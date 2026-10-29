# app/security_events.py
"""
HMAC-SHA256 event signing and verification.

Purpose
-------
Every security event (failed login, unauthorized access, etc.) is signed
before it is stored or forwarded.  This lets any component that later
consumes the event verify that it has not been tampered with.

Design decisions
----------------
- Uses Python's built-in `hmac` and `hashlib` — no extra dependency.
- The secret key is read from Config, never hardcoded.
- Signatures are compared with `hmac.compare_digest` to prevent
  timing-based side-channel attacks.
- The secret is never included in the returned event dict, log messages,
  or Prometheus metrics.

Typical event structure
-----------------------
{
    "event_type": "failed_login",
    "timestamp":  "2026-10-13T11:05:00.123456",
    "details":    {"username": "admin", "ip": "127.0.0.1"},
    "hmac_sha256": "<hex digest>"          # added by sign_event()
}
"""

import hmac
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.config import Config

logger = logging.getLogger(__name__)


def _canonical_payload(event: dict) -> bytes:
    """
    Produce a stable, deterministic byte representation of an event dict
    *without* the 'hmac_sha256' field so we can compute or verify a signature.

    We use JSON with sorted keys so the output is the same regardless of
    insertion order.
    """
    payload = {k: v for k, v in event.items() if k != "hmac_sha256"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _compute_hmac(payload_bytes: bytes) -> str:
    """Return the HMAC-SHA256 hex digest for *payload_bytes*."""
    return hmac.new(
        Config.HMAC_SECRET_KEY.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()


def sign_event(event_type: str, details: dict[str, Any] | None = None) -> dict:
    """
    Build a security event dict, sign it, and return it.

    Parameters
    ----------
    event_type : str
        Short identifier for the event, e.g. "failed_login".
    details : dict, optional
        Any additional context.  Must be JSON-serialisable.

    Returns
    -------
    dict
        The event with an 'hmac_sha256' field appended.
    """
    event: dict[str, Any] = {
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": details or {},
    }
    payload_bytes = _canonical_payload(event)
    event["hmac_sha256"] = _compute_hmac(payload_bytes)

    # Log the event type but NOT the secret or raw signature value
    logger.info("Security event recorded: %s", event_type)
    return event


def verify_event(event: dict) -> bool:
    """
    Verify that *event* has a valid HMAC-SHA256 signature.

    Returns True if the signature is present and correct, False otherwise.
    Logs a warning (without the secret) if verification fails.
    """
    stored_hmac = event.get("hmac_sha256")
    if not stored_hmac:
        logger.warning("Event missing hmac_sha256 field: %s", event.get("event_type"))
        return False

    payload_bytes = _canonical_payload(event)
    expected_hmac = _compute_hmac(payload_bytes)

    valid = hmac.compare_digest(stored_hmac, expected_hmac)
    if not valid:
        logger.warning(
            "HMAC verification FAILED for event type '%s'. "
            "The event may have been tampered with.",
            event.get("event_type"),
        )
    return valid
