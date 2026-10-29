# app/metrics.py
"""
Prometheus metric definitions for CyberSentinel.

All metrics are defined once here and imported by routes.py.
Keeping definitions in one place makes it easy to understand what is
being measured and avoids duplicate-registration errors.

Metrics exposed at /metrics (scraped by Prometheus later):
  - Request counts (by route, method, status code)
  - Response latency histogram
  - Failed login attempts counter
  - Unauthorized / forbidden request counter
  - Application error counter
  - Security event counter
  - ML anomaly score gauge        (set by ml/detector.py)
  - ML anomaly detected flag       (set by ml/detector.py)
  - Rule-based anomaly detected    (set by ml/detector.py, independent of ML)
"""

from prometheus_client import Counter, Histogram, Gauge

# ---------------------------------------------------------------------------
# Traffic metrics
# ---------------------------------------------------------------------------

REQUEST_COUNT = Counter(
    "cybersentinel_request_total",
    "Total number of HTTP requests received.",
    ["method", "endpoint", "http_status"],
)

REQUEST_LATENCY = Histogram(
    "cybersentinel_request_latency_seconds",
    "HTTP request latency in seconds.",
    ["endpoint"],
    # Buckets tuned for a demo app: from 10 ms to 10 s
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ---------------------------------------------------------------------------
# Security event metrics
# ---------------------------------------------------------------------------

FAILED_LOGIN_COUNT = Counter(
    "cybersentinel_failed_login_total",
    "Total number of failed login attempts.",
)

UNAUTHORIZED_COUNT = Counter(
    "cybersentinel_unauthorized_total",
    "Total number of requests that received a 401 or 403 response.",
)

SECURITY_EVENT_COUNT = Counter(
    "cybersentinel_security_event_total",
    "Total number of security events recorded.",
    ["event_type"],
)

ERROR_COUNT = Counter(
    "cybersentinel_error_total",
    "Total number of application errors (5xx responses).",
)

# ---------------------------------------------------------------------------
# ML metrics — values set by ml/detector.py
# ---------------------------------------------------------------------------

ML_ANOMALY_SCORE = Gauge(
    "cybersentinel_ml_anomaly_score",
    "Latest anomaly score from the ML detector. "
    "Higher positive values indicate more abnormal behaviour.",
)

ML_ANOMALY_DETECTED = Gauge(
    "cybersentinel_ml_anomaly_detected",
    "1 if the ML detector (Isolation Forest) has flagged an anomaly, 0 otherwise.",
)

RULE_BASED_ANOMALY_DETECTED = Gauge(
    "cybersentinel_rule_based_anomaly_detected",
    "1 if the rule-based (threshold) detector has flagged an anomaly, 0 otherwise. "
    "Independent of the ML model — kept separate for comparison.",
)
