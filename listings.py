"""
Real estate listings.

Manually curated -- see listing_admin.py for how listings get added, and
the warning at the top of that file about where listing_url should (and
should NOT -- Zillow/Redfin/Realtor.com) point to. Direct IDX/MLS access
also requires an active real estate license, which rules that out too.
"""
from flask import Blueprint, jsonify

from models import Listing

listings_bp = Blueprint("listings", __name__, url_prefix="/api")


def _serialize(listing):
    return {
        "id": listing.id,
        "address": listing.address,
        "town": listing.town,
        "price": listing.price,
        "beds": listing.beds,
        "baths": listing.baths,
        "sqft": listing.sqft,
        "property_type": listing.property_type,
        "listing_url": listing.listing_url,
        "source_label": listing.source_label,
    }


@listings_bp.get("/listings")
def get_listings():
    listings = Listing.query.filter_by(active=True).order_by(Listing.created_at.desc()).all()
    return jsonify({"listings": [_serialize(l) for l in listings]}), 200
