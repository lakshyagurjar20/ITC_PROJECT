# ml/features.py
"""
Metric scraping and feature engineering for the ML anomaly detector.

Responsibility
--------------
1. Fetch the Flask app's /metrics endpoint (Prometheus text exposition format).
2. Parse the CyberSentinel-specific counters and histograms.
3. Compute per-second *rates* by diffing two consecutive snapshots.
4. Return an ordered feature vector ready for Isolation Forest.

Feature vector (7 values, always in this order):
  Index  Name                 What it captures
  -----  -------------------  -------------------------------------------------
    0    request_rate         HTTP requests per second (all endpoints combined)
    1    error_rate           5xx responses per second
    2    failed_login_rate    Failed /login attempts per second
    3    unauthorized_rate    401/403 responses per second
    4    security_event_rate  Signed security events per second
    5    avg_latency_ms       Average response latency in milliseconds
    6    error_ratio          Fraction of requests that were errors (0-1)

Why rates and not raw counters?
  Prometheus counters are cumulative and always increasing.
  The ML model needs numbers that reflect *current behaviour*, not history.
  Taking the per-second rate between two snapshots gives a value proportional
  to what is happening *right now*.
"""

import re
import time
import logging
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# URL of the Flask app's Prometheus metrics endpoint
METRICS_URL = "http://localhost:5000/metrics"

# Ordered list of feature names — must match the vector built in compute_features()
FEATURE_NAMES = [
    "request_rate",
    "error_rate",
    "failed_login_rate",
    "unauthorized_rate",
    "security_event_rate",
    "avg_latency_ms",
    "error_ratio",
]

# Regex that matches a Prometheus text-format data line:
#   some_metric_name{label="value",...} 42.0
# Groups: name (without labels), value
_LINE_RE = re.compile(
    r"^(?P<name>[a-zA-Z_][a-zA-Z0-9_:]*)"   # metric name
    r"(?:\{[^}]*\})?"                         # optional label set — ignored
    r"\s+"
    r"(?P<value>[+-]?(?:\d+\.?\d*|\.\d+)"    # numeric value
    r"(?:[eE][+-]?\d+)?|NaN|[+-]?Inf)"
)


# ---------------------------------------------------------------------------
# Prometheus text parser
# ---------------------------------------------------------------------------

def parse_metrics_text(text: str) -> dict[str, float]:
    """
    Parse a Prometheus exposition text blob.

    Returns a flat dict where:
    - Keys are metric names (without label sets).
    - Values are the **sum** of all label combinations for that metric name.

    Only metrics whose name starts with 'cybersentinel_' are kept.
    Comment lines (# HELP / # TYPE) and blank lines are skipped.

    Example
    -------
    Input (two label combos for the same metric):
        cybersentinel_request_total{endpoint="home",http_status="200"} 10.0
        cybersentinel_request_total{endpoint="login",http_status="401"} 3.0
    Output:
        {"cybersentinel_request_total": 13.0}
    """
    totals: dict[str, float] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        name = m.group("name")
        if not name.startswith("cybersentinel_"):
            continue
        try:
            value = float(m.group("value"))
        except ValueError:
            continue
        totals[name] = totals.get(name, 0.0) + value
    return totals


# ---------------------------------------------------------------------------
# Snapshot & scraper
# ---------------------------------------------------------------------------

@dataclass
class Snapshot:
    """Raw metric values captured at a single point in time."""
    timestamp: float = field(default_factory=time.monotonic)
    raw: dict[str, float] = field(default_factory=dict)


class MetricsScraper:
    """
    Fetches /metrics and converts pairs of consecutive snapshots into
    feature vectors.

    Call compute_features() repeatedly (e.g., every 10 seconds).
    The first call returns None because there is no previous snapshot
    to diff against yet.  Every subsequent call returns a (rates, vector) tuple.
    """

    def __init__(self, url: str = METRICS_URL, timeout: int = 5) -> None:
        self.url = url
        self.timeout = timeout
        self._prev: Optional[Snapshot] = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _scrape(self) -> Optional[Snapshot]:
        """GET /metrics and return a Snapshot, or None on any error."""
        try:
            with urllib.request.urlopen(self.url, timeout=self.timeout) as resp:
                text = resp.read().decode("utf-8")
            return Snapshot(timestamp=time.monotonic(), raw=parse_metrics_text(text))
        except Exception as exc:
            logger.warning("Metrics scrape failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def compute_features(self) -> Optional[tuple[dict[str, float], list[float]]]:
        """
        Scrape /metrics, compute per-second rates vs. the previous snapshot,
        and return (rates_dict, feature_vector).

        Returns None if:
        - The scrape failed (network error, Flask not up yet).
        - This is the very first call (no previous snapshot to diff against).
        - The elapsed time between snapshots is zero or negative.
        """
        current = self._scrape()
        if current is None:
            return None

        prev = self._prev
        self._prev = current          # always store for the next call

        if prev is None:
            logger.debug("First scrape stored; waiting for second to compute rates.")
            return None

        elapsed = current.timestamp - prev.timestamp
        if elapsed <= 0:
            return None

        # Helper: compute per-second rate for a cumulative counter.
        # max(0, ...) guards against counter resets (app restart).
        def rate(key: str) -> float:
            delta = current.raw.get(key, 0.0) - prev.raw.get(key, 0.0)
            return max(0.0, delta) / elapsed

        # --- Per-second rates for the 5 core counters ---
        request_rate        = rate("cybersentinel_request_total")
        error_rate          = rate("cybersentinel_error_total")
        failed_login_rate   = rate("cybersentinel_failed_login_total")
        unauthorized_rate   = rate("cybersentinel_unauthorized_total")
        security_event_rate = rate("cybersentinel_security_event_total")

        # --- Average latency from histogram sum / count ---
        lat_sum_d   = max(0.0,
            current.raw.get("cybersentinel_request_latency_seconds_sum",   0.0)
            - prev.raw.get("cybersentinel_request_latency_seconds_sum",    0.0))
        lat_count_d = max(0.0,
            current.raw.get("cybersentinel_request_latency_seconds_count", 0.0)
            - prev.raw.get("cybersentinel_request_latency_seconds_count",  0.0))
        avg_latency_ms = (lat_sum_d / lat_count_d * 1000.0) if lat_count_d > 0 else 0.0

        # --- Error ratio (0–1) ---
        error_ratio = (error_rate / request_rate) if request_rate > 0 else 0.0

        rates = {
            "request_rate":        request_rate,
            "error_rate":          error_rate,
            "failed_login_rate":   failed_login_rate,
            "unauthorized_rate":   unauthorized_rate,
            "security_event_rate": security_event_rate,
            "avg_latency_ms":      avg_latency_ms,
            "error_ratio":         error_ratio,
        }

        # Build the ordered feature vector
        vector = [rates[name] for name in FEATURE_NAMES]
        return rates, vector
