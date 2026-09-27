"""
One-off schema migration for the real chat room.

Unlike migrate.py (which could safely drop and recreate the incidents
table), the `users` table now holds real signed-up accounts, so this
migration only ADDS the new columns/table -- it never drops anything.

Run this once, on Render, via the Web Shell:
    python migrate_chat.py
"""
from sqlalchemy import inspect, text

from app import create_app
from models import ChatMessage, db

app = create_app()
with app.app_context():
    inspector = inspect(db.engine)
    existing_columns = {c["name"] for c in inspector.get_columns("users")}

    new_columns = [
        ("chat_strikes", "INTEGER NOT NULL DEFAULT 0"),
        ("chat_last_strike_at", "TIMESTAMP NULL"),
        ("chat_banned", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("chat_moderation_exempt", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ]

    for name, ddl_type in new_columns:
        if name not in existing_columns:
            db.session.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl_type}"))
            print(f"added users.{name}")
        else:
            print(f"users.{name} already exists, skipping")

    db.session.commit()

    # Creates the chat_messages table if it doesn't exist yet; leaves
    # every other existing table alone.
    ChatMessage.__table__.create(db.engine, checkfirst=True)
    print("done")
