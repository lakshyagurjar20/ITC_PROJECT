# app/routes.py
"""
HTTP routes for the CyberSentinel demo application.

Each route is designed to simulate a specific scenario that produces
measurable changes in Prometheus metrics.

Scenario mapping
----------------
Scenario 1 – Normal browsing   : GET /  and  GET /api/data
Scenario 2 – Failed logins     : POST /login  with wrong credentials
Scenario 3 – Unauthorized accs : GET /admin   without the X-Auth-Token header
Scenario 4 – High request vol  : Repeat any route quickly (use the load script)
Scenario 5 – Error spikes      : GET /error
Scenario 6 – Latency increase  : GET /slow
"""

import time
import logging
from functools import wraps

from flask import Blueprint, request, jsonify

from app.config import Config
from app.metrics import (
    REQUEST_COUNT,
    REQUEST_LATENCY,
    FAILED_LOGIN_COUNT,
    UNAUTHORIZED_COUNT,
    SECURITY_EVENT_COUNT,
    ERROR_COUNT,
)
from app.security_events import sign_event, verify_event

logger = logging.getLogger(__name__)

bp = Blueprint("main", __name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _track_request(endpoint: str, status: int, start_time: float) -> None:
    """Update REQUEST_COUNT and REQUEST_LATENCY for a completed request."""
    elapsed = time.perf_counter() - start_time
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=endpoint,
        http_status=str(status),
    ).inc()
    REQUEST_LATENCY.labels(endpoint=endpoint).observe(elapsed)


def track(endpoint_name: str):
    """
    Decorator that wraps a route and records latency + request count.

    Usage:
        @bp.route("/foo")
        @track("foo")
        def foo():
            return jsonify({"ok": True}), 200
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            response, status = fn(*args, **kwargs)
            _track_request(endpoint_name, status, start)
            return response, status
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/", methods=["GET"])
@track("home")
def home():
    """Scenario 1 – Normal browsing: application health check."""
    return jsonify({
        "service": "CyberSentinel Demo App",
        "status": "ok",
        "version": "0.1.0",
    }), 200


@bp.route("/api/data", methods=["GET"])
@track("api_data")
def api_data():
    """Scenario 1 – Normal browsing: returns mock application data."""
    return jsonify({
        "items": ["record_1", "record_2", "record_3"],
        "count": 3,
    }), 200


@bp.route("/login", methods=["POST"])
def login():
    """
    Scenario 2 – Repeated failed login attempts.

    Accepts JSON body: {"username": "...", "password": "..."}
    Returns 200 on success, 401 on failure.
    """
    start = time.perf_counter()
    body = request.get_json(silent=True) or {}
    username = body.get("username", "")
    password = body.get("password", "")

    if username == Config.DEMO_USERNAME and password == Config.DEMO_PASSWORD:
        # Successful login — no security event needed
        _track_request("login", 200, start)
        return jsonify({"status": "authenticated", "token": "demo-token-abc123"}), 200

    # --- Failed login ---
    FAILED_LOGIN_COUNT.inc()
    SECURITY_EVENT_COUNT.labels(event_type="failed_login").inc()

    # Build and sign a security event
    event = sign_event(
        "failed_login",
        details={"username": username, "ip": request.remote_addr},
    )

    # Demonstrate that verify_event works (useful for testing)
    if not verify_event(event):
        logger.error("Freshly signed event failed verification — this should never happen.")

    logger.warning("Failed login attempt for username='%s' from %s", username, request.remote_addr)
    _track_request("login", 401, start)
    return jsonify({"error": "Invalid credentials"}), 401


@bp.route("/admin", methods=["GET"])
def admin():
    """
    Scenario 3 – Unauthorized / forbidden access.

    A valid 'X-Auth-Token: demo-token-abc123' header is required.
    Returns 403 when the token is absent or wrong.
    """
    start = time.perf_counter()
    token = request.headers.get("X-Auth-Token", "")

    if token != "demo-token-abc123":
        UNAUTHORIZED_COUNT.inc()
        SECURITY_EVENT_COUNT.labels(event_type="unauthorized_access").inc()

        event = sign_event(
            "unauthorized_access",
            details={"ip": request.remote_addr, "path": "/admin"},
        )
        verify_event(event)  # self-check

        logger.warning("Unauthorized access attempt to /admin from %s", request.remote_addr)
        _track_request("admin", 403, start)
        return jsonify({"error": "Forbidden. Valid X-Auth-Token header required."}), 403

    _track_request("admin", 200, start)
    return jsonify({"secret": "admin panel data", "users": ["admin", "alice", "bob"]}), 200


@bp.route("/error", methods=["GET"])
def trigger_error():
    """
    Scenario 5 – Application error spike.

    Intentionally returns a 500 response to simulate server errors.
    """
    start = time.perf_counter()
    ERROR_COUNT.inc()
    SECURITY_EVENT_COUNT.labels(event_type="application_error").inc()

    event = sign_event("application_error", details={"route": "/error"})
    verify_event(event)

    logger.error("Simulated application error triggered.")
    _track_request("error", 500, start)
    return jsonify({"error": "Simulated internal server error"}), 500


@bp.route("/slow", methods=["GET"])
@track("slow")
def slow_response():
    """
    Scenario 6 – Increased response latency.

    Sleeps for 2 seconds to push the latency histogram into higher buckets.
    """
    time.sleep(2)
    return jsonify({"status": "ok", "note": "This response was intentionally delayed 2 s."}), 200


# ---------------------------------------------------------------------------
# Generic 404 handler — keeps error counter and metrics consistent
# ---------------------------------------------------------------------------

@bp.app_errorhandler(404)
def not_found(err):
    start = time.perf_counter()
    _track_request("not_found", 404, start)
    return jsonify({"error": "Route not found"}), 404
