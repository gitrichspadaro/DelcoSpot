"""
Manual real estate listing management, until there's an admin UI.

IMPORTANT -- where listing_url/source_label should point: NOT Zillow,
Redfin, or Realtor.com. Their Terms of Use each restrict displaying their
listing data (not just automated scraping of it -- Zillow's terms bar
"displaying any other Zillow Companies' data without our prior written
approval", which covers facts typed in by hand too) and restrict linking
to their listing pages to real-estate-licensed sites, which this isn't.
Use a source that's actually fine with it instead:
  - The listing agent/brokerage's own site (most want the exposure)
  - An FSBO platform that explicitly allows link-outs
  - A direct arrangement with a local agent who's okayed the listing

Usage (on Render, via the delcospot-api Web Shell -- type these bare,
no quotes, since the shell mangles pasted quotes/multi-line input; use
underscores in place of spaces for fields, this script un-escapes them):

    python listing_admin.py list
        Lists all listings (including inactive ones) with their id.

    python listing_admin.py add 412_Kedron_Ave Ridley_Township 289000 3 1.5 1420 Twin https://www.janedoerealty.com/listings/412-kedron-ave Jane_Doe_Realty
        Adds a listing. Args in order: address, town, price, beds, baths,
        sqft, property_type, listing_url, source_label -- sqft and
        source_label are optional (pass "-" to skip sqft and still
        provide source_label). listing_url should be the agent's/
        brokerage's own page for the listing, not an aggregator site.

    python listing_admin.py deactivate 3
        Hides listing id 3 from the site without deleting it (e.g. it
        sold, or the listing needs to be pulled temporarily).

    python listing_admin.py activate 3
        Un-hides it.

    python listing_admin.py delete 3
        Permanently deletes listing id 3.
"""
import sys

from app import create_app
from models import Listing, db

app = create_app()


def _unescape(s):
    return s.replace("_", " ") if s != "-" else None


def list_listings():
    listings = Listing.query.order_by(Listing.created_at.desc()).all()
    for l in listings:
        flag = "" if l.active else "  [inactive]"
        print(f"[{l.id}] {l.address} - {l.town} - ${l.price:,}{flag}")


def add_listing(args):
    if len(args) < 7:
        print("Usage: add <address> <town> <price> <beds> <baths> <sqft> <property_type> <listing_url> [source_label]")
        return
    address = _unescape(args[0])
    town = _unescape(args[1])
    price = int(args[2])
    beds = int(args[3])
    baths = float(args[4])
    sqft_raw = args[5]
    sqft = int(sqft_raw) if sqft_raw != "-" else None
    property_type = _unescape(args[6])
    listing_url = args[7] if len(args) > 7 else None
    source_label = _unescape(args[8]) if len(args) > 8 else None

    if not listing_url:
        print("A listing_url is required -- the agent's/brokerage's own page for this listing, not Zillow/Redfin/Realtor.com (see the warning at the top of this file).")
        return

    listing = Listing(
        address=address, town=town, price=price, beds=beds, baths=baths,
        sqft=sqft, property_type=property_type, listing_url=listing_url,
        source_label=source_label,
    )
    db.session.add(listing)
    db.session.commit()
    print(f"Added listing [{listing.id}] {listing.address}.")


def set_active(listing_id, active):
    listing = db.session.get(Listing, listing_id)
    if not listing:
        print(f"No listing with id {listing_id}.")
        return
    listing.active = active
    db.session.commit()
    print(f"{'Activated' if active else 'Deactivated'} [{listing.id}] {listing.address}.")


def delete_listing(listing_id):
    listing = db.session.get(Listing, listing_id)
    if not listing:
        print(f"No listing with id {listing_id}.")
        return
    print(f"Deleting [{listing.id}] {listing.address}.")
    db.session.delete(listing)
    db.session.commit()
    print("done")


if __name__ == "__main__":
    with app.app_context():
        args = sys.argv[1:]
        if not args or args[0] == "list":
            list_listings()
        elif args[0] == "add":
            add_listing(args[1:])
        elif args[0] == "deactivate" and len(args) == 2:
            set_active(int(args[1]), False)
        elif args[0] == "activate" and len(args) == 2:
            set_active(int(args[1]), True)
        elif args[0] == "delete" and len(args) == 2:
            delete_listing(int(args[1]))
        else:
            print(__doc__)
