"""
Manual chat moderation, until there's an admin UI.

Usage (on Render, via the delcospot-api Web Shell -- type these bare,
no quotes, since the shell mangles pasted quotes/multi-line input):

    python chat_admin.py list
        Lists the 30 most recent chat messages with their id, author,
        and text, so you can find the id of one to remove.

    python chat_admin.py delete 42
        Deletes chat message id 42 permanently.

    python chat_admin.py unban someone@example.com
        Clears a user's chat ban and strike count (for the "a moderator
        has to lift it" part of the room rules).
"""
import sys

from app import create_app
from models import ChatMessage, User, db

app = create_app()


def list_messages():
    messages = ChatMessage.query.order_by(ChatMessage.id.desc()).limit(30).all()
    for m in reversed(messages):
        print(f"[{m.id}] {m.created_at.isoformat()}Z  {m.author_name}: {m.text!r}")


def delete_message(message_id):
    message = db.session.get(ChatMessage, message_id)
    if not message:
        print(f"No message with id {message_id}.")
        return
    print(f"Deleting [{message.id}] {message.author_name}: {message.text!r}")
    db.session.delete(message)
    db.session.commit()
    print("done")


def unban_user(email):
    user = User.query.filter_by(email=email.strip().lower()).first()
    if not user:
        print(f"No user with email {email}.")
        return
    user.chat_banned = False
    user.chat_strikes = 0
    user.chat_last_strike_at = None
    db.session.commit()
    print(f"Unbanned {user.email}.")


if __name__ == "__main__":
    with app.app_context():
        args = sys.argv[1:]
        if not args or args[0] == "list":
            list_messages()
        elif args[0] == "delete" and len(args) == 2:
            delete_message(int(args[1]))
        elif args[0] == "unban" and len(args) == 2:
            unban_user(args[1])
        else:
            print(__doc__)
