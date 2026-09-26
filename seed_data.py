"""
One-off script to load sample incident data for local testing and to give
the live site something real to display before a real scraper/feed is
built (see Implementation Checklist: "county dispatch feed scraper").

Run it with:
    python seed_data.py

Safe to run more than once locally -- it clears existing incidents first
so you don't pile up duplicates. Do NOT run this against the production
database once real scraped data exists; it's a seed script for demo/dev
data only.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

from app import create_app
from models import db, Incident

TOWNS = ["Media", "Chester", "Upper Darby", "Havertown", "Springfield", "Ridley Park"]

SAMPLE_INCIDENTS = [
    dict(incident_type="Structure Fire", priority="High", status="Active",
         location="200 Block W State St", town="Media",
         unit="Media Fire Co. 1, Engine 32", narrative="Reported smoke from second floor.",
         latitude=39.9165, longitude=-75.3878, hours_ago=1),
    dict(incident_type="Motor Vehicle Accident", priority="Medium", status="Cleared",
         location="Baltimore Pike & Providence Rd", town="Springfield",
         unit="Springfield PD, Medic 22", narrative="Two vehicles, minor injuries reported.",
         latitude=39.9312, longitude=-75.3277, hours_ago=4),
    dict(incident_type="Medical Emergency", priority="High", status="Active",
         location="100 Block Long Lane", town="Upper Darby",
         unit="Upper Darby Medic 52", narrative="Difficulty breathing, ALS dispatched.",
         latitude=39.9598, longitude=-75.2727, hours_ago=0.5),
    dict(incident_type="Gas Leak", priority="Medium", status="Active",
         location="Township Line Rd", town="Havertown",
         unit="Oakmont Fire Co.", narrative="PECO en route to confirm and shut off.",
         latitude=39.9926, longitude=-75.3057, hours_ago=2),
    dict(incident_type="Brush Fire", priority="Low", status="Cleared",
         location="Ridley Creek State Park", town="Ridley Park",
         unit="Ridley Park Fire Co.", narrative="Small brush fire, contained quickly.",
         latitude=39.8779, longitude=-75.3227, hours_ago=30),
    dict(incident_type="Structure Fire", priority="High", status="Cleared",
         location="9th & Barclay St", town="Chester",
         unit="Chester Fire Dept., Ladder 5", narrative="Vacant row home, extinguished.",
         latitude=39.8495, longitude=-75.3563, hours_ago=50),
    dict(incident_type="Motor Vehicle Accident", priority="Low", status="Cleared",
         location="MacDade Blvd", town="Ridley Park",
         unit="Ridley Park PD", narrative="Single vehicle, no injuries.",
         latitude=39.8817, longitude=-75.3266, hours_ago=72),
    dict(incident_type="Water Rescue", priority="High", status="Cleared",
         location="Crum Creek", town="Media",
         unit="Media Fire Co., Swiftwater Team", narrative="Person rescued, transported for evaluation.",
         latitude=39.9143, longitude=-75.3903, hours_ago=96),
]


def seed():
    app = create_app()
    with app.app_context():
        deleted = db.session.query(Incident).delete()
        now = datetime.now(timezone.utc)

        for row in SAMPLE_INCIDENTS:
            hours_ago = row.pop("hours_ago")
            incident = Incident(occurred_at=now - timedelta(hours=hours_ago), **row)
            db.session.add(incident)

        db.session.commit()
        print(f"Cleared {deleted} old incident(s). Inserted {len(SAMPLE_INCIDENTS)} sample incident(s).")


if __name__ == "__main__":
    seed()
