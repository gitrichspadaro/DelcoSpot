"""
DelcoSpot API - minimal starting point.

This is intentionally small: a health check and a root route, just enough
to prove the pipeline (GitHub -> Render) works end to end. Real routes,
database models, and auth get added on top of this as the Implementation
Checklist items get built out.
"""
import os
from flask import Flask, jsonify


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

    return app


app = create_app()

if __name__ == "__main__":
    # Render sets the PORT environment variable at runtime; default to
    # 5000 for local development.
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
