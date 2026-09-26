"""
One-off schema migration: drops and recreates the `incidents` table so it
picks up new columns added to the Incident model (incident_number,
updated_at) as part of building the real dispatch scraper.

Safe to run because there's no real historical incident data in the table
yet -- it's either empty or holds stale seed/demo rows. Once real
scraped data exists, a tool like Flask-Migrate should be used instead of
drop-and-recreate for any future schema changes.

Run this once, on Render, via the Web Shell:
    python migrate.py
"""
from app import create_app
from models import db, Incident

app = create_app()
with app.app_context():
    Incident.__table__.drop(db.engine, checkfirst=True)
    db.create_all()
    print("done")
