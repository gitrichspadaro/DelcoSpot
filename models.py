"""
Database models for DelcoSpot.

Kept intentionally simple for now: enough to store real users and real
incidents. Fields will grow as more of the site gets wired up to a real
backend (chat messages, listings, jobs, etc.).
"""
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<User {self.email}>"


class Incident(db.Model):
    __tablename__ = "incidents"

    id = db.Column(db.Integer, primary_key=True)
    incident_type = db.Column(db.String(120), nullable=False)
    priority = db.Column(db.String(20), nullable=False)       # High / Medium / Low
    status = db.Column(db.String(20), nullable=False, default="Active")  # Active / Cleared
    location = db.Column(db.String(255), nullable=False)
    town = db.Column(db.String(120), nullable=False, index=True)
    unit = db.Column(db.String(255))
    narrative = db.Column(db.Text)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    occurred_at = db.Column(db.DateTime, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Incident {self.incident_type} @ {self.town}>"
