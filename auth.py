"""
Authentication routes: signup now, login next.

Kept as its own blueprint so auth-related routes have one clear home as
more get added (login, logout, password reset, etc.).
"""
import re

from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, User

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_PASSWORD_LENGTH = 128  # bound input size; also limits hashing-cost abuse


@auth_bp.post("/signup")
def signup():
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    errors = {}
    if not name:
        errors["name"] = "Name is required."
    if not email or not EMAIL_RE.match(email):
        errors["email"] = "A valid email is required."
    if len(password) < 8:
        errors["password"] = "Password must be at least 8 characters."
    elif len(password) > MAX_PASSWORD_LENGTH:
        errors["password"] = f"Password must be {MAX_PASSWORD_LENGTH} characters or fewer."

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
