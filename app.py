"""
DelcoSpot API - minimal starting point.

This is intentionally small: a health check and a root route, just enough
to prove the pipeline (GitHub -> Render) works end to end. Real routes,
database models, and auth get added on top of this as the Implementation
Checklist items get built out.
"""
import os
from flask import Flask, jsonify

import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

from models import db, User, Incident
from auth import auth_bp

SENTRY_DSN = os.environ.get("SENTRY_DSN")

if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[FlaskIntegration()],
        # Percentage of requests to trace for performance monitoring.
        # 1.0 = 100%; fine at this scale, dial down once there's real traffic.
        traces_sample_rate=1.0,
    )


def create_app():
    app = Flask(__name__)

    # DATABASE_URL is read from the environment, never hardcoded, so the
    # real connection string never ends up in the code or in Git. Falls
    # back to a local SQLite file if it's not set, so the app still runs
    # for quick local testing without Postgres.
    database_url = os.environ.get("DATABASE_URL", "sqlite:///dev.db")
    # Some providers still hand out "postgres://" URLs; SQLAlchemy 1.4+
    # requires "postgresql://" instead, so rewrite it if needed.
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

    db.init_app(app)

    with app.app_context():
        # Creates the users/incidents tables if they don't exist yet.
        # Fine for this early stage; once the schema is stabilizing,
        # switch to Flask-Migrate for real migrations instead.
        db.create_all()

    app.register_blueprint(auth_bp)

    @app.get("/")
    def index():
        return jsonify({
            "service": "DelcoSpot API",
            "status": "ok",
            "message": "DelcoSpot backend is running. See /healthz for the health check endpoint.",
        })

    @app.get("/healthz")
    def healthz():
        # Render (or any uptime monitor) can poll this to confirm the
        # service is alive, including that the database connection works.
        try:
            db.session.execute(db.text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False
        status_code = 200 if db_ok else 503
        return jsonify({"status": "healthy" if db_ok else "database unreachable"}), status_code

    @app.get("/debug-sentry")
    def trigger_error():
        # Temporary route to confirm Sentry is actually receiving errors.
        # Safe to delete once you've seen one show up in the Sentry dashboard.
        1 / 0

    return app


app = create_app()

if __name__ == "__main__":
    # Render sets the PORT environment variable at runtime; default to
    # 5000 for local development.
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


