"""
Delco dispatch feed scraper.

Pulls live incident data from the same public API that powers
https://www.delcodispat.ch/ (found via browser dev tools -- it's an
undocumented but public, unauthenticated, CORS-open JSON endpoint) and
loads it into our own `incidents` table.

Why this exists: the raw feed pages each *unit* separately, so one real
incident (a car accident, a fire) shows up as several entries sharing the
same `incidentNumber` -- one per fire company/medic unit paged for it.
This script groups those back into a single incident row per
`incidentNumber`, which is the actual value-add DelcoSpot provides over
the raw feed ("organizes the data better than delcodispat.ch", per the
original brief).

Run on a schedule (a Render Cron Job hitting `python scraper.py`, roughly
every 1-2 minutes). Safe to run repeatedly: incidents are upserted by
`incident_number`, so re-scraping the same incident just updates it
(e.g. picks up a newly-paged additional unit) instead of duplicating it.

Known limitations (see the Parking Lot / Implementation Checklist):
  - The feed has no explicit "priority" field, so `priority` is left
    unset for now rather than guessed.
  - The feed has no explicit "cleared" event, so every scraped incident
    is stored as status "Active". Real status tracking is a future step.
  - Each scrape only looks at the most recent PAGES_PER_RUN pages of the
    feed (paginating backward via pagingToken), which is plenty to catch
    new activity between runs but is NOT a full historical backfill.
    A one-time deeper backfill (following pagingToken further back) is
    a separate, future task if full history is wanted.
"""
import os
import json
from datetime import datetime, timedelta, timezone

import requests

from app import create_app
from models import db, Incident

FEED_URL = "https://api.delcodispat.ch/api/d/pa/delco"
REQUEST_TIMEOUT_SECONDS = 15

# How many pages (of ~20 raw entries each) to pull per run. A few pages of
# overlap with the previous run is intentional and harmless -- upserts
# just re-save incidents we've already seen.
PAGES_PER_RUN = int(os.environ.get("SCRAPER_PAGES_PER_RUN", "3"))

# The feed's times are local Eastern time (the county is in PA) with no
# timezone offset given. Delco doesn't observe a different UTC offset
# depending on DST in a way we can safely guess in code without a tz
# database lookup, so we use a fixed US/Eastern conversion via zoneinfo.
from zoneinfo import ZoneInfo
EASTERN = ZoneInfo("America/New_York")


def fetch_page(paging_token=""):
    """Fetch one page of the raw feed. Returns (pages, next_paging_token)."""
    response = requests.get(
        FEED_URL,
        params={"pagingToken": paging_token or "", "isDescending": "true"},
        headers={"Accept": "application/json"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("pages", []), data.get("pagingToken")


def _extra_field(additional_fields, key):
    for field in additional_fields or []:
        if field.get("key") == key:
            return field.get("value")
    return None


def _parse_occurred_at(date_received, time_str):
    """Combine the feed's separate date/time strings into a UTC datetime."""
    if not date_received or not time_str:
        return datetime.now(timezone.utc)
    try:
        naive = datetime.strptime(f"{date_received} {time_str}", "%m/%d/%Y %H:%M:%S")
        local = naive.replace(tzinfo=EASTERN)
        return local.astimezone(timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def group_pages_into_incidents(pages):
    """
    Collapse raw per-unit feed entries into one dict per real incident,
    keyed by incidentNumber. Entries missing an incidentNumber are
    skipped -- without it we have no reliable way to dedupe or upsert
    them, and they're rare (a handful of malformed feed rows at most).
    """
    grouped = {}

    for page in pages:
        incident_number = page.get("incidentNumber")
        if not incident_number:
            continue

        unit = page.get("stationIdentifier") or page.get("station") or ""
        location = page.get("location") or ""
        if not location or location == "/":
            cross1 = page.get("crossStreet1") or ""
            cross2 = page.get("crossStreet2") or ""
            location = " & ".join(p for p in (cross1, cross2) if p).title() or "Location unavailable"

        latitude = _extra_field(page.get("additionalFields"), "Latitude")
        longitude = _extra_field(page.get("additionalFields"), "Longitude")

        if incident_number not in grouped:
            grouped[incident_number] = {
                "incident_number": incident_number,
                "incident_type": (page.get("nature") or "Unknown").title(),
                "location": location,
                "town": page.get("municipality") or "Unknown",
                "units": [],
                "narrative": page.get("notes") or None,
                "latitude": float(latitude) if latitude else None,
                "longitude": float(longitude) if longitude else None,
                "occurred_at": _parse_occurred_at(page.get("dateReceived"), page.get("time")),
            }

        entry = grouped[incident_number]
        if unit and unit not in entry["units"]:
            entry["units"].append(unit)

    for entry in grouped.values():
        entry["unit"] = ", ".join(entry.pop("units")) or None

    return grouped


def upsert_incidents(grouped):
    """Insert new incidents, update existing ones (matched by incident_number)."""
    inserted = 0
    updated = 0

    for incident_number, fields in grouped.items():
        existing = Incident.query.filter_by(incident_number=incident_number).first()
        if existing:
            existing.unit = fields["unit"]
            existing.narrative = fields["narrative"]
            existing.location = fields["location"]
            existing.town = fields["town"]
            existing.latitude = fields["latitude"]
            existing.longitude = fields["longitude"]
            updated += 1
        else:
            db.session.add(Incident(
                incident_number=fields["incident_number"],
                incident_type=fields["incident_type"],
                location=fields["location"],
                town=fields["town"],
                unit=fields["unit"],
                narrative=fields["narrative"],
                latitude=fields["latitude"],
                longitude=fields["longitude"],
                occurred_at=fields["occurred_at"],
            ))
            inserted += 1

    db.session.commit()
    return inserted, updated


def run(pages_per_run=PAGES_PER_RUN):
    app = create_app()
    with app.app_context():
        all_pages = []
        paging_token = ""
        for _ in range(pages_per_run):
            pages, next_token = fetch_page(paging_token)
            if not pages:
                break
            all_pages.extend(pages)
            if not next_token:
                break
            paging_token = next_token

        grouped = group_pages_into_incidents(all_pages)
        inserted, updated = upsert_incidents(grouped)
        print(f"Scraped {len(all_pages)} raw feed entries -> "
              f"{len(grouped)} incidents ({inserted} new, {updated} updated).")


if __name__ == "__main__":
    run()
