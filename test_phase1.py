# test_phase1.py
"""
Phase 1 verification script.

Run this while the Flask app is running to exercise every scenario
and print a clear pass/fail summary.

Usage:
    python test_phase1.py
"""

import json
import sys
import time
import urllib.request
import urllib.error

BASE = "http://localhost:5000"


def get(path: str, headers: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(f"{BASE}{path}", headers=headers or {})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def post(path: str, body: dict) -> tuple[int, dict]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def check(name: str, got_status: int, expected_status: int, body: dict) -> bool:
    ok = got_status == expected_status
    symbol = "[PASS]" if ok else "[FAIL]"
    print(f"  {symbol}  {name:<40}  HTTP {got_status}  {list(body.keys())}")
    return ok


def main() -> None:
    print("\n" + "=" * 65)
    print("  CyberSentinel Phase 1 -- Verification")
    print("=" * 65)

    results = []

    # Scenario 1 -- Normal browsing
    s, b = get("/")
    results.append(check("GET / (home)", s, 200, b))

    s, b = get("/api/data")
    results.append(check("GET /api/data", s, 200, b))

    # Scenario 2 -- Successful login
    s, b = post("/login", {"username": "admin", "password": "secret123"})
    results.append(check("POST /login (correct creds)", s, 200, b))

    # Scenario 2 -- Failed login
    s, b = post("/login", {"username": "admin", "password": "wrongpassword"})
    results.append(check("POST /login (wrong creds -> 401)", s, 401, b))

    # Scenario 3 -- Unauthorized
    s, b = get("/admin")
    results.append(check("GET /admin (no token -> 403)", s, 403, b))

    # Scenario 3 -- Authorized
    s, b = get("/admin", headers={"X-Auth-Token": "demo-token-abc123"})
    results.append(check("GET /admin (with token -> 200)", s, 200, b))

    # Scenario 5 -- Error spike
    s, b = get("/error")
    results.append(check("GET /error (-> 500)", s, 500, b))

    # 404
    s, b = get("/notexist")
    results.append(check("GET /notexist (-> 404)", s, 404, b))

    # Scenario 6 -- Slow response
    print("\n  (slow route: waiting ~2 s...)")
    t0 = time.perf_counter()
    s, b = get("/slow")
    elapsed = time.perf_counter() - t0
    ok = s == 200 and elapsed >= 1.8
    symbol = "[PASS]" if ok else "[FAIL]"
    print(f"  {symbol}  {'GET /slow (-> 200, >=2 s delay)':<40}  HTTP {s}  elapsed={elapsed:.2f}s")
    results.append(ok)

    # Metrics endpoint
    req = urllib.request.Request(f"{BASE}/metrics")
    try:
        with urllib.request.urlopen(req) as resp:
            text = resp.read().decode()
        has_metric = "cybersentinel_request_total" in text
        symbol = "[PASS]" if has_metric else "[FAIL]"
        print(f"  {symbol}  {'GET /metrics (contains custom metrics)':<40}", "OK" if has_metric else "MISSING")
        results.append(has_metric)
    except Exception as exc:
        print(f"  [FAIL]  GET /metrics                              ERROR: {exc}")
        results.append(False)

    # Summary
    passed = sum(results)
    total = len(results)
    print("\n" + "-" * 65)
    print(f"  Result: {passed}/{total} checks passed")
    if passed == total:
        print("  All checks passed! Phase 1 is working correctly.")
    else:
        print("  Some checks failed. Review the output above.")
    print("=" * 65 + "\n")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
