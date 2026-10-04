"""
County-wide chat room.

Real and shared: every message is stored in the database and every
signed-up member sees the same room, polling for new messages every few
seconds (there's no websocket server here, so polling is the simple,
reliable way to get "live enough" updates without extra infrastructure).

Moderation happens before a message is ever stored -- a blocked message
never reaches the room or the database, so there's nothing to clean up
after the fact. The rules enforced here are a first pass at what the
room rules shown on the page promise:
  - No vulgar/profane language, slurs, or harassment.
  - No phone numbers (a common way private info leaks into a public room).
  - No message that's mostly links (a simple, low-false-positive proxy
    for spam/advertising, without trying to guess intent).
"You appear to be sharing a home address" detection is NOT attempted:
free-text address matching without a mapping/geocoding service throws
false positives constantly (any street-shaped phrase, a business address,
a park name) and would block far more real conversation than it would
ever catch. If that becomes a real problem, revisit with real data on
what's actually getting through.

Two strikes within 24 hours bans the account from the room (matching the
text already shown to users), until a moderator manually clears it by
resetting chat_strikes/chat_banned on the user record -- there's no
admin UI for that yet.
"""
import re
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from models import ChatMessage, db
from extensions import limiter

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")

MAX_MESSAGE_LENGTH = 300
STRIKE_WINDOW_HOURS = 24
MESSAGES_PER_POLL = 50

# General vulgar/profane words, plus slurs and harassment phrases. Single
# words are matched as whole words (see WORD_RES below) so this doesn't
# flag substrings inside unrelated words (e.g. blocking "ass" must not
# flag "class" or "assess"). Multi-word phrases are matched as substrings.
BLOCKED_WORDS = [
    "fuck", "shit", "bitch", "bastard", "asshole", "dumbass", "jackass",
    "cunt", "dick", "piss", "whore", "slut", "bullshit", "goddamn",
    "idiot", "stupid", "moron", "retard", "faggot", "nigger", "nigga",
    "loser",
]
BLOCKED_PHRASES = [
    "shut up", "kill yourself", "kys", "hate you",
]

# Common single-character substitutions people use to dodge a word filter
# (e.g. "fuuuck", "f*ck", "sh1t"). This is a light normalization pass, not
# a full evasion-proof system -- it catches the obvious cases without
# trying to be clever about every possible workaround.
LEET_MAP = str.maketrans({"@": "a", "4": "a", "3": "e", "1": "i", "!": "i", "0": "o", "$": "s"})
REPEAT_RE = re.compile(r"(.)\1+")  # any run of a repeated character
NON_WORD_GAP_RE = re.compile(r"[\s*._-]+")

WORD_RES = [re.compile(r"\b" + re.escape(w) + r"\b") for w in BLOCKED_WORDS]

PHONE_RE = re.compile(r"(?<!\d)(\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})(?!\d)")
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


def _normalize(text):
    # This normalized form is only used to check for a match -- the
    # original text is what actually gets stored/shown, untouched.
    lower = text.lower().translate(LEET_MAP)
    deduped = REPEAT_RE.sub(r"\1", lower)           # "fuuuck" -> "fuck"
    collapsed = NON_WORD_GAP_RE.sub("", deduped)    # "f u c k" / "f-u-c-k" -> "fuck"
    return deduped, collapsed


def moderate(text):
    """Returns a rejection reason string, or None if the message is fine."""
    lower, collapsed = _normalize(text)

    for word_re, word in zip(WORD_RES, BLOCKED_WORDS):
        if word_re.search(lower) or word in collapsed:
            return "vulgar or abusive language"

    for phrase in BLOCKED_PHRASES:
        if phrase in lower:
            return "abusive language"

    if PHONE_RE.search(text):
        return "a phone number"

    urls = URL_RE.findall(text)
    if urls and len(" ".join(urls)) > len(text) * 0.5:
        return "link spam"

    return None


def _serialize(message):
    return {
        "id": message.id,
        "author": message.author_name,
        "text": message.text,
        "created_at": message.created_at.isoformat() + "Z",
        "mine": message.user_id == current_user.id,
    }


def _register_strike(user):
    now = datetime.now(timezone.utc)
    within_window = (
        user.chat_last_strike_at is not None
        and now - user.chat_last_strike_at.replace(tzinfo=timezone.utc) < timedelta(hours=STRIKE_WINDOW_HOURS)
    )
    user.chat_strikes = user.chat_strikes + 1 if within_window else 1
    user.chat_last_strike_at = now
    if user.chat_strikes >= 2:
        user.chat_banned = True
    db.session.commit()
    return user.chat_banned


@chat_bp.get("/messages")
@login_required
def get_messages():
    since_id = request.args.get("since_id", type=int)
    query = ChatMessage.query.order_by(ChatMessage.id.asc())
    if since_id:
        query = query.filter(ChatMessage.id > since_id)
        messages = query.limit(200).all()
    else:
        messages = query.order_by(ChatMessage.id.desc()).limit(MESSAGES_PER_POLL).all()
        messages.reverse()

    return jsonify({
        "banned": current_user.chat_banned and not current_user.chat_moderation_exempt,
        "messages": [_serialize(m) for m in messages],
    }), 200


@chat_bp.post("/messages")
@login_required
@limiter.limit("20 per minute")
def post_message():
    exempt = current_user.chat_moderation_exempt

    if current_user.chat_banned and not exempt:
        return jsonify({"errors": {"chat": "You've been banned from the chat room."}}), 403

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()

    if not text:
        return jsonify({"errors": {"text": "Message can't be empty."}}), 400
    if len(text) > MAX_MESSAGE_LENGTH:
        return jsonify({"errors": {"text": f"Messages are limited to {MAX_MESSAGE_LENGTH} characters."}}), 400

    reason = None if exempt else moderate(text)
    if reason:
        banned = _register_strike(current_user)
        if banned:
            return jsonify({
                "errors": {"chat": "Second violation. You've been banned from this room."},
                "banned": True,
            }), 403
        return jsonify({
            "errors": {"chat": f"Message blocked ({reason}). One more violation results in a ban."},
            "banned": False,
        }), 422

    message = ChatMessage(user_id=current_user.id, author_name=current_user.name, text=text)
    db.session.add(message)
    db.session.commit()

    return jsonify(_serialize(message)), 201
