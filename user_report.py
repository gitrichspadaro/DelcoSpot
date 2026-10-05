"""
Signup report: total users, plus everyone who signed up in the last 24 hours.

Run by hand on the Render Web Shell:   python user_report.py
Or on a schedule as a Render Cron Job (see render.yaml) -- the output lands
in that cron job's Logs tab each run. Needs the same DATABASE_URL
environment variable as delcospot-api; nothing is hardcoded here.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app import create_app
from models import User

EASTERN = ZoneInfo("America/New_York")


def _as_utc(dt):
    # created_at is stored as a naive UTC datetime.
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def run():
    app = create_app()
    with app.app_context():
        total = User.query.count()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent = (
            User.query.filter(User.created_at >= cutoff.replace(tzinfo=None))
            .order_by(User.created_at.desc())
            .all()
        )

        print(f"Total users: {total}")
        print(f"New in the last 24 hours: {len(recent)}")
        for u in recent:
            when = _as_utc(u.created_at).astimezone(EASTERN).strftime("%Y-%m-%d %I:%M %p ET")
            print(f"  [{u.id}] {u.name} <{u.email}> - {when}")


if __name__ == "__main__":
    run()
