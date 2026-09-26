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
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user

from models import Incident

incidents_bp = Blueprint("incidents", __name__, url_prefix="/api")

ANONYMOUS_WINDOW_HOURS = 24


def _serialize(incident):
    return {
        "id": incident.id,
        "incident_type": incident.incident_type,
        "priority": incident.priority,
        "status": incident.status,
        "location": incident.location,
        "town": incident.town,
        "unit": incident.unit,
        "narrative": incident.narrative,
        "latitude": incident.latitude,
        "longitude": incident.longitude,
        "occurred_at": incident.occurred_at.isoformat(),
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

    priority = request.args.get("priority")
    if priority:
        query = query.filter(Incident.priority.ilike(priority))

    status = request.args.get("status")
    if status:
        query = query.filter(Incident.status.ilike(status))

    incidents = query.order_by(Incident.occurred_at.desc()).limit(500).all()

    return jsonify({
        "access": "full_history" if is_full_access else "last_24_hours",
        "count": len(incidents),
        "incidents": [_serialize(i) for i in incidents],
    }), 200
