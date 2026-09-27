"""
Nightlife venue directory.

Real and manually curated -- see venue_admin.py for how venues get added.
No "tonight's specials," "awards," or social-feed data is served here:
none of that can be sourced reliably for small local venues without each
one individually integrating with us, so rather than show fabricated
placeholder data, those features were removed. Venues link out to their
own site/Instagram instead, so visitors get real, current info straight
from the source.
"""
from flask import Blueprint, jsonify

from models import Venue

venues_bp = Blueprint("venues", __name__, url_prefix="/api")


def _serialize(venue):
    return {
        "id": venue.id,
        "name": venue.name,
        "town": venue.town,
        "category": venue.category,
        "blurb": venue.blurb,
        "website_url": venue.website_url,
        "instagram_url": venue.instagram_url,
    }


@venues_bp.get("/venues")
def get_venues():
    venues = Venue.query.filter_by(active=True).order_by(Venue.name.asc()).all()
    return jsonify({"venues": [_serialize(v) for v in venues]}), 200
