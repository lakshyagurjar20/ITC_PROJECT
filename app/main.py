# app/main.py
"""
Entry point for the CyberSentinel Flask application.

Run with:
    python -m app.main

What this file does:
1. Validates that required environment variables are present.
2. Creates the Flask app and registers the route Blueprint.
3. Mounts the Prometheus /metrics endpoint.
4. Starts the ML anomaly detector background thread.
5. Starts the development server.
"""

import logging
import os
import sys

from flask import Flask
from prometheus_client import make_wsgi_app
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from app.config import Config
from app.routes import bp


def create_app() -> Flask:
    """
    Application factory.

    Keeping app creation in a function (rather than at module level) makes
    it easy to create separate instances for testing later.
    """
    # 1. Validate config — fail fast if HMAC secret is missing
    Config.validate()

    # 2. Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )

    # 3. Create the Flask app
    app = Flask(__name__)
    app.config["DEBUG"] = Config.DEBUG

    # 4. Register the route Blueprint
    app.register_blueprint(bp)

    # 5. Mount Prometheus metrics at /metrics using WSGI middleware.
    #    This is the standard, recommended approach with prometheus-client.
    #    Prometheus will scrape http://localhost:5000/metrics
    app.wsgi_app = DispatcherMiddleware(
        app.wsgi_app,
        {"/metrics": make_wsgi_app()},
    )

    return app


if __name__ == "__main__":
    flask_app = create_app()

    # -----------------------------------------------------------------------
    # Start the ML anomaly detector thread.
    #
    # Guard: Werkzeug's reloader forks a child process and sets WERKZEUG_RUN_MAIN
    # in it.  Without this guard the detector would start in BOTH the parent
    # (reloader watcher) and the child (actual server), giving two threads
    # scraping /metrics and writing to the same Prometheus gauges.
    # We only start the detector in the child (or when not in debug mode).
    # -----------------------------------------------------------------------
    in_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if in_reloader_child or not Config.DEBUG:
        from ml.detector import AnomalyDetector
        detector = AnomalyDetector()
        detector.start()

    print("\n" + "=" * 62)
    print("  CyberSentinel Demo App -- Phase 2")
    print("=" * 62)
    print("  Home          : http://localhost:5000/")
    print("  Login         : POST http://localhost:5000/login")
    print("  Admin         : GET  http://localhost:5000/admin")
    print("  Error trigger : GET  http://localhost:5000/error")
    print("  Slow response : GET  http://localhost:5000/slow")
    print("  Metrics       : http://localhost:5000/metrics")
    print("-" * 62)
    print("  ML detector   : background thread (starts after 12 s)")
    print("  Training      : after 20 samples (~3.5 min at 10 s interval)")
    print("=" * 62 + "\n")

    # Use Werkzeug's built-in server for development.
    # Do NOT use this in production.
    flask_app.run(
        host="0.0.0.0",
        port=5000,
        debug=Config.DEBUG,
        # Exclude tools/, prometheus data, and grafana from the file watcher
        # to prevent the reload loop when those directories change.
        exclude_patterns=["*/tools/*", "*/prometheus/*", "*/grafana/*"],
    )
