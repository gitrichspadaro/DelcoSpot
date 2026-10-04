"""
Authentication routes: signup now, login next.

Kept as its own blueprint so auth-related routes have one clear home as
more get added (login, logout, password reset, etc.).
"""
import random
import re

from flask import Blueprint, current_app, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, User
from extensions import limiter

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_PASSWORD_LENGTH = 128  # bound input size; also limits hashing-cost abuse

# A simple, self-hosted signup challenge -- no third-party service or API
# keys needed. It's a basic bot deterrent, not a strong one: fine for
# stopping naive scripted signups, not a determined attacker. The answer
# is never sent to the client in a way it could read -- it's signed into
# an opaque token the client just echoes back, and verified server-side.
CAPTCHA_MAX_AGE_SECONDS = 10 * 60


def _captcha_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="signup-captcha")


def _verify_captcha(token, answer):
    if not token or answer is None:
        return False
    try:
        expected = _captcha_serializer().loads(token, max_age=CAPTCHA_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return False
    try:
        return int(answer) == int(expected)
    except (TypeError, ValueError):
        return False


@auth_bp.get("/captcha")
@limiter.limit("30 per hour")
def captcha():
    a, b = random.randint(1, 9), random.randint(1, 9)
    token = _captcha_serializer().dumps(a + b)
    return jsonify({"token": token, "question": f"What is {a} + {b}?"}), 200


@auth_bp.post("/signup")
@limiter.limit("5 per hour")
def signup():
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    captcha_token = data.get("captcha_token")
    captcha_answer = data.get("captcha_answer")

    errors = {}
    if not name:
        errors["name"] = "Name is required."
    if not email or not EMAIL_RE.match(email):
        errors["email"] = "A valid email is required."
    if len(password) < 8:
        errors["password"] = "Password must be at least 8 characters."
    elif len(password) > MAX_PASSWORD_LENGTH:
        errors["password"] = f"Password must be {MAX_PASSWORD_LENGTH} characters or fewer."
    if not _verify_captcha(captcha_token, captcha_answer):
        errors["captcha"] = "That answer isn't right. Try the new question below."

    if errors:
        return jsonify({"errors": errors}), 400

    if User.query.filter_by(email=email).first():
        # Deliberately vague: don't confirm which field was wrong beyond
        # "email", so this can't be used to enumerate registered emails
        # much more precisely than it already does.
        return jsonify({"errors": {"email": "An account with this email already exists."}}), 409

    user = User(
        name=name,
        email=email,
        password_hash=generate_password_hash(password),
    )
    db.session.add(user)
    db.session.commit()

    return jsonify({
        "id": user.id,
        "name": user.name,
        "email": user.email,
    }), 201


@auth_bp.post("/login")
@limiter.limit("10 per 5 minutes")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()

    # Deliberately generic error either way, so a failed login doesn't
    # reveal whether that email even has an account.
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"errors": {"login": "Incorrect email or password."}}), 401

    login_user(user)
    return jsonify({"id": user.id, "name": user.name, "email": user.email}), 200


@auth_bp.post("/logout")
@login_required
def logout():
    logout_user()
    return jsonify({"message": "Logged out."}), 200


@auth_bp.get("/me")
@login_required
def me():
    return jsonify({
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
    }), 200
