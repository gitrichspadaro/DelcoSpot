"""
Database models for DelcoSpot.

Kept intentionally simple for now: enough to store real users and real
incidents. Fields will grow as more of the site gets wired up to a real
backend (chat messages, listings, jobs, etc.).
"""
from datetime import datetime, timezone

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Chat moderation state. `chat_last_strike_at` lets the second-strike
    # check look back only 24 hours, matching the room rules shown to
    # users ("a second flag inside 24 hours issues a ban").
    chat_strikes = db.Column(db.Integer, nullable=False, default=0)
    chat_last_strike_at = db.Column(db.DateTime, nullable=True)
    chat_banned = db.Column(db.Boolean, nullable=False, default=False)

    def __repr__(self):
        return f"<User {self.email}>"


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    # Snapshot the name at post time so a later name change doesn't rewrite
    # history, and so the room still works even if the user record changes.
    author_name = db.Column(db.String(120), nullable=False)
    text = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def __repr__(self):
        return f"<ChatMessage {self.id} by user {self.user_id}>"


class Incident(db.Model):
    __tablename__ = "incidents"

    id = db.Column(db.Integer, primary_key=True)

    # The county dispatch feed's own incident number (e.g. "F26070982").
    # Unique + indexed so the scraper can upsert: the same incident often
    # pages several units separately, and re-running the scraper on a
    # schedule will see the same incident again as it updates. This is
    # how we avoid creating duplicate rows.
    incident_number = db.Column(db.String(50), unique=True, index=True, nullable=True)

    incident_type = db.Column(db.String(120), nullable=False)
    # The raw feed has no priority field of its own, so this stays optional
    # until a real priority signal (e.g. keyword rules on `incident_type`)
    # gets built -- see the Parking Lot.
    priority = db.Column(db.String(20), nullable=True)         # High / Medium / Low
    # Likewise, the feed has no explicit "cleared" event, so every scraped
    # incident currently lands as "Active". Real status tracking (e.g. an
    # incident aging out after N hours of no updates) is a future step.
    status = db.Column(db.String(20), nullable=False, default="Active")  # Active / Cleared
    location = db.Column(db.String(255), nullable=False)
    town = db.Column(db.String(120), nullable=False, index=True)
    unit = db.Column(db.String(255))
    narrative = db.Column(db.Text)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    occurred_at = db.Column(db.DateTime, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                            onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Incident {self.incident_type} @ {self.town}>"
