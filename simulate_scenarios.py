# simulate_scenarios.py
"""
Scenario simulator for CyberSentinel.

Generates controlled bursts of traffic to produce measurable changes in
Prometheus metrics and exercise the ML anomaly detector.

Usage:
    python simulate_scenarios.py [scenario_number]

Scenarios:
    1  Normal traffic         - Mix of home/api/data requests
    2  Failed login attack    - Repeated wrong-credential POST /login
    3  Unauthorized access    - Repeated GET /admin without token
    4  High request volume    - Very fast normal requests
    5  Error spike            - Repeated GET /error
    6  Latency observation    - Sequential GET /slow requests
    0  Run ALL scenarios sequentially (good for ML training data)

Run with no argument to see an interactive menu.
"""

import json
import sys
import time
import urllib.request
import urllib.error

BASE = "http://localhost:5000"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _request(method: str, path: str, body: dict | None = None,
             headers: dict | None = None) -> tuple[int, str]:
    """Make an HTTP request and return (status_code, response_text)."""
    data = json.dumps(body).encode() if body else None
    h = {"Content-Type": "application/json"} if body else {}
    if headers:
        h.update(headers)
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as exc:
        print(f"  [ERROR] {exc}")
        return 0, ""


def get(path: str, headers: dict | None = None) -> tuple[int, str]:
    return _request("GET", path, headers=headers)


def post(path: str, body: dict) -> tuple[int, str]:
    return _request("POST", path, body=body)


def separator(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  Scenario: {title}")
    print(f"{'=' * 60}")


# ---------------------------------------------------------------------------
# Individual scenarios
# ---------------------------------------------------------------------------

def scenario_1_normal(n: int = 30) -> None:
    """Normal browsing traffic — mix of home and API requests."""
    separator("1 — Normal Traffic")
    print(f"  Sending {n} normal requests...")
    for i in range(n):
        s1, _ = get("/")
        s2, _ = get("/api/data")
        if i % 5 == 0:
            print(f"  [{i+1:3d}/{n}] GET / -> {s1}   GET /api/data -> {s2}")
        time.sleep(0.3)
    print("  Done. Check cybersentinel_request_total in /metrics.")


def scenario_2_failed_logins(n: int = 20) -> None:
    """Repeated failed login attempts — increments failed_login_total."""
    separator("2 — Failed Login Attack")
    print(f"  Sending {n} failed login attempts...")
    for i in range(n):
        s, _ = post("/login", {"username": "admin", "password": f"badpass_{i}"})
        if i % 5 == 0:
            print(f"  [{i+1:3d}/{n}] POST /login -> {s}")
        time.sleep(0.2)
    print("  Done. Check cybersentinel_failed_login_total in /metrics.")


def scenario_3_unauthorized(n: int = 20) -> None:
    """Repeated unauthorized access — increments unauthorized_total."""
    separator("3 — Unauthorized Access")
    print(f"  Sending {n} requests to /admin without token...")
    for i in range(n):
        s, _ = get("/admin")
        if i % 5 == 0:
            print(f"  [{i+1:3d}/{n}] GET /admin -> {s}")
        time.sleep(0.2)
    print("  Done. Check cybersentinel_unauthorized_total in /metrics.")


def scenario_4_high_volume(n: int = 100) -> None:
    """High request volume — rapid-fire GET / requests."""
    separator("4 — High Request Volume")
    print(f"  Sending {n} requests as fast as possible...")
    for i in range(n):
        s, _ = get("/")
        if i % 20 == 0:
            print(f"  [{i+1:3d}/{n}] GET / -> {s}")
    print("  Done. Check cybersentinel_request_total in /metrics.")


def scenario_5_errors(n: int = 15) -> None:
    """Application error spike — increments error_total."""
    separator("5 — Error Spike")
    print(f"  Triggering {n} server errors...")
    for i in range(n):
        s, _ = get("/error")
        if i % 5 == 0:
            print(f"  [{i+1:3d}/{n}] GET /error -> {s}")
        time.sleep(0.3)
    print("  Done. Check cybersentinel_error_total in /metrics.")


def scenario_6_latency(n: int = 3) -> None:
    """Slow response requests — pushes latency histogram into high buckets."""
    separator("6 — Latency Increase")
    print(f"  Sending {n} slow requests (~2 s each)...")
    for i in range(n):
        t0 = time.perf_counter()
        s, _ = get("/slow")
        elapsed = time.perf_counter() - t0
        print(f"  [{i+1}/{n}] GET /slow -> {s}  elapsed={elapsed:.2f}s")
    print("  Done. Check cybersentinel_request_latency_seconds in /metrics.")


def run_all() -> None:
    """Run all scenarios sequentially — good for generating ML training data."""
    separator("ALL SCENARIOS (sequential)")
    print("  This generates varied traffic to help the ML model see normal")
    print("  and anomalous behaviour. Takes about 2-3 minutes.")
    print()

    # Phase A: ~90 seconds of normal traffic (ML training window)
    print("  [A] Generating normal traffic for ML training...")
    scenario_1_normal(n=50)

    time.sleep(5)

    # Phase B: Attack scenarios
    print("\n  [B] Running attack scenarios...")
    scenario_2_failed_logins(n=20)
    time.sleep(3)
    scenario_3_unauthorized(n=20)
    time.sleep(3)
    scenario_4_high_volume(n=100)
    time.sleep(3)
    scenario_5_errors(n=15)
    time.sleep(3)
    scenario_6_latency(n=3)

    print("\n" + "=" * 60)
    print("  All scenarios complete.")
    print("  Check the Flask console for [ML] and [RULE] log lines.")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

MENU = {
    "1": ("Normal traffic",          scenario_1_normal),
    "2": ("Failed login attack",      scenario_2_failed_logins),
    "3": ("Unauthorized access",      scenario_3_unauthorized),
    "4": ("High request volume",      scenario_4_high_volume),
    "5": ("Error spike",              scenario_5_errors),
    "6": ("Latency increase",         scenario_6_latency),
    "0": ("Run ALL scenarios",        run_all),
}


def main() -> None:
    if len(sys.argv) > 1:
        choice = sys.argv[1].strip()
    else:
        print("\n  CyberSentinel — Scenario Simulator")
        print("  " + "-" * 40)
        for key, (name, _) in MENU.items():
            print(f"  {key}  {name}")
        print()
        choice = input("  Enter scenario number: ").strip()

    entry = MENU.get(choice)
    if not entry:
        print(f"  Unknown scenario '{choice}'. Choose from: {list(MENU.keys())}")
        sys.exit(1)

    name, fn = entry
    print(f"\n  Running: {name}")
    fn()


if __name__ == "__main__":
    main()
