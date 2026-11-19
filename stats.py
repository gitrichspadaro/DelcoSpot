"""
Public dispatch statistics: aggregate counts from the incidents table.

Routes:
  GET /api/stats/dispatch   JSON aggregates (cached for 10 minutes)
  GET /stats/              the statistics page (frontend/stats/index.html)

Only counts leave this module. No addresses, unit IDs, narratives or
individual incidents are returned. Any group with fewer than MIN_COUNT calls
is dropped so that a rare call can't be traced to one event.
"""
import os
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, jsonify, send_from_directory

from incidents import classify_service
from models import Incident

stats_bp = Blueprint("stats", __name__)

EASTERN = ZoneInfo("America/New_York")
MIN_COUNT = 5
CACHE_SECONDS = 600
WINDOW_DAYS = 30
TOP_N = 10

_cache = {"data": None, "at": 0.0}
_FRONTEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")


def pretty_type(text):
    """Title-case a call type but keep the county's EMS acronyms upper-case."""
    out = text.strip().title()
    for word in ("Als", "Bls", "Ems", "Ems/", "Cpr"):
        out = out.replace(word, word.upper()) if word in out else out
    return out


def _to_eastern(naive_utc):
    return naive_utc.replace(tzinfo=timezone.utc).astimezone(EASTERN)


def _visible(counter):
    """Keep only groups with at least MIN_COUNT calls, largest first."""
    return [{"name": k, "count": v} for k, v in counter.most_common() if v >= MIN_COUNT]


def build_stats(now_utc=None):
    now_utc = now_utc or datetime.now(timezone.utc).replace(tzinfo=None)
    window_start = now_utc - timedelta(days=WINDOW_DAYS)
    rows = (Incident.query
            .with_entities(Incident.occurred_at, Incident.town, Incident.incident_type, Incident.unit)
            .filter(Incident.occurred_at >= window_start)
            .all())

    last7_start = now_utc - timedelta(days=7)
    prev7_start = now_utc - timedelta(days=14)
    last7 = prev7 = 0
    services, towns, types, hours, days = Counter(), Counter(), Counter(), Counter(), Counter()

    for occurred, town, incident_type, unit in rows:
        if occurred >= last7_start:
            last7 += 1
        elif occurred >= prev7_start:
            prev7 += 1
        services[classify_service(incident_type, unit)] += 1
        if town:
            towns[town] += 1
        if incident_type:
            types[pretty_type(incident_type)] += 1
        local = _to_eastern(occurred)
        hours[local.hour] += 1
        days[local.date().isoformat()] += 1

    change = None
    if prev7 >= MIN_COUNT:
        change = round((last7 - prev7) / prev7 * 100)

    # One bucket per day for the last WINDOW_DAYS days, oldest first, zero-filled.
    today_local = _to_eastern(now_utc).date()
    daily = []
    for back in range(WINDOW_DAYS - 1, -1, -1):
        d = (today_local - timedelta(days=back)).isoformat()
        daily.append({"date": d, "count": days.get(d, 0)})

    return {
        "generated_at": now_utc.isoformat(timespec="seconds") + "Z",
        "window_days": WINDOW_DAYS,
        "min_count": MIN_COUNT,
        "totals": {
            "last_7_days": last7,
            "previous_7_days": prev7,
            "change_percent": change,
            "last_30_days": len(rows),
        },
        "by_service": _visible(services),
        "by_town": _visible(towns)[:TOP_N],
        "by_incident_type": _visible(types)[:TOP_N],
        "by_hour_eastern": [{"hour": h, "count": hours.get(h, 0)} for h in range(24)],
        "daily": daily,
    }


def cached_stats():
    now = time.time()
    if _cache["data"] is None or now - _cache["at"] > CACHE_SECONDS:
        _cache["data"] = build_stats()
        _cache["at"] = now
    return _cache["data"]


@stats_bp.get("/api/stats/dispatch")
def dispatch_stats():
    resp = jsonify(cached_stats())
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@stats_bp.get("/stats/")
def stats_page():
    stats_dir = os.path.join(_FRONTEND, "stats")
    response = send_from_directory(stats_dir, "index.html")
    response.headers["Cache-Control"] = "no-cache"
    return response
