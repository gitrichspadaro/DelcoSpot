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
        # service is alive. Expand this later to also check the database
        # connection once one exists.
        return jsonify({"status": "healthy"}), 200

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

