"""
Incident feed routes.

This is DelcoSpot's flagship feature: an organized, filterable view of
emergency dispatch activity across Delaware County. The core access rule
from the original site plan is enforced here, server-side:

  - Anonymous (not logged in) visitors can only see incidents from the
    last 24 hours.
  - Logged-in users can see full history.

On the static demo, this rule only existed in JavaScript (which anyone
could bypass by opening dev tools). Here, the check happens in the query
itself, so there's no way for a client to see more than it's allowed to
just by editing the page.
"""
import re
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user

from models import Incident

incidents_bp = Blueprint("incidents", __name__, url_prefix="/api")

ANONYMOUS_WINDOW_HOURS = 24


# The county feed has no priority or severity field, so instead of guessing
# one we show which service responded (Fire / EMS / Police). That comes from
# the county's own call type, falling back to the kind of units dispatched.
EMS_TYPE_WORDS = ("EMS", "ALS", "BLS", "MEDICAL", "AMBULANCE", "CARDIAC", "OVERDOSE")
FIRE_TYPE_WORDS = ("FIRE", "ALARM", "SMOKE", "GAS", "HAZMAT", "HAZ MAT", "RESCUE",
                   "WIRES", "WIRE", "EXPLOSION", "CO", "CARBON MONOXIDE", "ODOR",
                   "ELEVATOR", "FD")
POLICE_TYPE_WORDS = ("POLICE", "PD")
EMS_UNIT_WORDS = ("MEDIC", "AMBULANCE", "MICU", "EMS", "BLS", "ALS")
FIRE_UNIT_WORDS = ("COMPANY", "ENGINE", "LADDER", "TRUCK", "SQUAD", "RESCUE", "TOWER",
                   "CHIEF", "FIRE", "TANKER", "BRUSH", "QUINT")


def _has_word(text, words):
    """True if any of `words` appears in `text` as a whole word, so "ALS"
    matches "ALS-EMS FALL" but not "FALSE ALARM"."""
    return any(re.search(r"\b" + re.escape(word) + r"\b", text) for word in words)


def classify_service(incident_type, unit):
    call = (incident_type or "").upper().replace("-", " ")
    # "ALS-EMS ...", "BLS-EMS ..." -- the county's own EMS call codes.
    if _has_word(call, EMS_TYPE_WORDS):
        return "EMS"
    # Checked before police: "ASSIST FD TO ASSIST POLICE" is a fire
    # department call (the fire company is what gets sent).
    if _has_word(call, FIRE_TYPE_WORDS):
        return "Fire"
    if _has_word(call, POLICE_TYPE_WORDS):
        return "Police"

    units = (unit or "").upper()
    if _has_word(units, FIRE_UNIT_WORDS):
        return "Fire"
    if _has_word(units, EMS_UNIT_WORDS):
        return "EMS"
    return "Other"


def _serialize(incident):
    return {
        "id": incident.id,
        "incident_number": incident.incident_number,
        "incident_type": incident.incident_type,
        "service": classify_service(incident.incident_type, incident.unit),
        "status": incident.status,
        "location": incident.location,
        "town": incident.town,
        "unit": incident.unit,
        "narrative": incident.narrative,
        "latitude": incident.latitude,
        "longitude": incident.longitude,
        # occurred_at is stored as a naive UTC datetime (see scraper.py), so
        # isoformat() alone would omit the timezone and let a browser
        # misread it as local time. Appending "Z" makes the UTC explicit.
        "occurred_at": incident.occurred_at.isoformat() + "Z",
    }


@incidents_bp.get("/incidents")
def get_incidents():
    query = Incident.query

    # This is the real access-control check the original demo faked in
    # JS. It runs here regardless of what the client sends, so an
    # anonymous request can never pull more than 24 hours of data.
    is_full_access = current_user.is_authenticated
    if not is_full_access:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=ANONYMOUS_WINDOW_HOURS)
        query = query.filter(Incident.occurred_at >= cutoff)

    # Optional filters -- available to everyone, they just narrow within
    # whatever window the user is already allowed to see.
    town = request.args.get("town")
    if town:
        query = query.filter(Incident.town.ilike(town))

    status = request.args.get("status")
    if status:
        query = query.filter(Incident.status.ilike(status))

    incidents = query.order_by(Incident.occurred_at.desc()).limit(500).all()

    return jsonify({
        "access": "full_history" if is_full_access else "last_24_hours",
        "count": len(incidents),
        "incidents": [_serialize(i) for i in incidents],
    }), 200
