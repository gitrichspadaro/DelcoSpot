"""
Manual venue directory management, until there's an admin UI.

Usage (on Render, via the delcospot-api Web Shell -- type these bare,
no quotes, since the shell mangles pasted quotes/multi-line input; use
underscores in place of spaces for fields, this script un-escapes them):

    python venue_admin.py list
        Lists all venues (including inactive ones) with their id.

    python venue_admin.py add "The_Bootleg_Room" Media Bar "Corner_taproom_with_live_music_most_weekends." https://example.com https://instagram.com/bootlegroom
        Adds a venue. Args after the name are: town, category, blurb,
        website_url, instagram_url -- category, blurb, website_url and
        instagram_url are all optional (pass "-" to skip one and still
        provide a later one).

    python venue_admin.py deactivate 3
        Hides venue id 3 from the site without deleting it (e.g. it
        closed, or the listing needs to be pulled temporarily).

    python venue_admin.py activate 3
        Un-hides it.

    python venue_admin.py delete 3
        Permanently deletes venue id 3.
"""
import sys

from app import create_app
from models import Venue, db

app = create_app()


def _unescape(s):
    return s.replace("_", " ") if s != "-" else None


def list_venues():
    venues = Venue.query.order_by(Venue.name.asc()).all()
    for v in venues:
        flag = "" if v.active else "  [inactive]"
        print(f"[{v.id}] {v.name} - {v.town} ({v.category or 'no category'}){flag}")


def add_venue(args):
    if len(args) < 2:
        print("Usage: add <name> <town> [category] [blurb] [website_url] [instagram_url]")
        return
    name = _unescape(args[0])
    town = _unescape(args[1])
    category = _unescape(args[2]) if len(args) > 2 else None
    blurb = _unescape(args[3]) if len(args) > 3 else None
    website_url = _unescape(args[4]) if len(args) > 4 else None
    instagram_url = _unescape(args[5]) if len(args) > 5 else None

    venue = Venue(
        name=name, town=town, category=category, blurb=blurb,
        website_url=website_url, instagram_url=instagram_url,
    )
    db.session.add(venue)
    db.session.commit()
    print(f"Added venue [{venue.id}] {venue.name}.")


def set_active(venue_id, active):
    venue = db.session.get(Venue, venue_id)
    if not venue:
        print(f"No venue with id {venue_id}.")
        return
    venue.active = active
    db.session.commit()
    print(f"{'Activated' if active else 'Deactivated'} [{venue.id}] {venue.name}.")


def delete_venue(venue_id):
    venue = db.session.get(Venue, venue_id)
    if not venue:
        print(f"No venue with id {venue_id}.")
        return
    print(f"Deleting [{venue.id}] {venue.name}.")
    db.session.delete(venue)
    db.session.commit()
    print("done")


if __name__ == "__main__":
    with app.app_context():
        args = sys.argv[1:]
        if not args or args[0] == "list":
            list_venues()
        elif args[0] == "add":
            add_venue(args[1:])
        elif args[0] == "deactivate" and len(args) == 2:
            set_active(int(args[1]), False)
        elif args[0] == "activate" and len(args) == 2:
            set_active(int(args[1]), True)
        elif args[0] == "delete" and len(args) == 2:
            delete_venue(int(args[1]))
        else:
            print(__doc__)
