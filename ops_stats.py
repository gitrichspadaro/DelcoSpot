"""
Operational snapshot: users, chat and dispatch-feed numbers in one screen.

Run by hand on the Render Web Shell:   python ops_stats.py
Counts only -- no names or email addresses are printed. Needs the same
DATABASE_URL environment variable as delcospot-api.
"""
from datetime import datetime, timedelta, timezone

from app import create_app
from models import db, User, ChatMessage, Incident


def _naive(dt):
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt is not None and dt.tzinfo else dt


def _ago(now, dt):
    if dt is None:
        return "never"
    minutes = int((now - _naive(dt)).total_seconds() // 60)
    if minutes < 120:
        return f"{minutes} min ago"
    if minutes < 48 * 60:
        return f"{minutes // 60} hours ago"
    return f"{minutes // 1440} days ago"


def run():
    app = create_app()
    with app.app_context():
        now = datetime.now(timezone.utc).replace(tzinfo=None)  # timestamps are stored as naive UTC
        day, week = now - timedelta(hours=24), now - timedelta(days=7)

        def count(model, since=None):
            q = model.query
            return q.filter(model.created_at >= since).count() if since else q.count()

        print(f"DelcoSpot operational snapshot - {now.isoformat(timespec='minutes')}Z")
        print()
        print("Users")
        print(f"  total:              {count(User)}")
        print(f"  new, last 24 hours: {count(User, day)}")
        print(f"  new, last 7 days:   {count(User, week)}")
        print()
        print("Chat")
        print(f"  messages total:     {count(ChatMessage)}")
        print(f"  messages, 7 days:   {count(ChatMessage, week)}")
        posters = (db.session.query(ChatMessage.user_id)
                   .filter(ChatMessage.created_at >= week).distinct().count())
        print(f"  people posting, 7d: {posters}")
        print(f"  last message:       {_ago(now, db.session.query(db.func.max(ChatMessage.created_at)).scalar())}")
        print()
        print("Dispatch feed")
        print(f"  incidents total:    {count(Incident)}")
        print(f"  imported, 24 hours: {count(Incident, day)}")
        print(f"  imported, 7 days:   {count(Incident, week)}")
        print(f"  last import:        {_ago(now, db.session.query(db.func.max(Incident.created_at)).scalar())}")
        # Service (Fire / EMS) is derived per incident, not stored, so count it here.
        from collections import Counter
        from incidents import classify_service
        rows = (db.session.query(Incident.incident_type, Incident.unit)
                .filter(Incident.created_at >= week).all())
        for service, n in Counter(classify_service(t, u) for t, u in rows).most_common():
            print(f"    {service or 'Unknown'}: {n} in 7 days")


if __name__ == "__main__":
    run()
