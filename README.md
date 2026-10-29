# CyberSentinel - Runtime Security Monitoring

CyberSentinel is an academic security observability demo built with Flask, Prometheus, Grafana, and an Isolation Forest anomaly detector. It provides controlled routes and a scenario simulator for generating normal activity, failed logins, unauthorized access, traffic bursts, application errors, and slow responses. Prometheus collects the application metrics and Grafana displays them. Security event payloads are signed and verified with HMAC-SHA256.

The intended flow is: generate application traffic, observe telemetry in Prometheus/Grafana, compare rule-based and ML anomaly signals, and preserve the integrity of security event data. Email or provider notifications and durable security event storage are future work.

This is a local academic demo. Credentials and the admin token are simulated. The Flask built-in server is for development only. Do not expose it to the public internet or use it to protect real accounts.

## Implementation progress

| Area | Status | Current state / remaining work |
| --- | --- | --- |
| Flask app and scenarios | Implemented | Health/data routes, simulated login/admin, error and slow routes, plus a scenario driver. |
| Prometheus telemetry | Implemented | Request totals, latency histogram, failed-login, unauthorized, error, and security-event counters; ML and rule-based gauges. |
| Grafana dashboard | Implemented | Provisioned 22-panel dashboard for request, latency, errors, security, and anomaly metrics. |
| Rule-based detector | Implemented | Threshold rules run alongside the ML detector. Tune thresholds and add alerting/reporting. |
| ML detector | Prototype implemented | Background metric scraper creates seven features and trains/retrains Isolation Forest. Add controlled evaluation, model lifecycle, and false-positive measurements. |
| HMAC event integrity | Partially implemented | Events are signed and verified in-process. Durable storage, audit history, key rotation, and verification reporting remain. |
| Email/webhook notifications | Not implemented | Add a delivery provider, configuration, retries, and visible delivery status. |
| Docker stack | Configured for local demo | Compose app, Prometheus, and Grafana use separate Docker-specific monitoring configuration. Verify the complete runtime on the target machine. |
| Automated checks | Basic smoke script | test_phase1.py exercises ten route/metrics checks against a running app. Add unit and end-to-end automation. |
| Production readiness | Remaining | Use a production WSGI server; replace demo credentials; protect endpoints and dashboards; plan secrets, retention, backups, and deployment. |

The detector needs warm-up data. Its defaults collect at 10-second intervals and fit after 20 feature samples, so expect roughly 3-4 minutes after startup before trained scores appear. Generate normal traffic first. Training on anomalous traffic may reduce detection quality. This model is a demonstration and has not been validated as threat detection.

## Requirements

- Windows 10/11 with PowerShell (commands below are PowerShell).
- Docker Desktop with the Linux container engine and Docker Compose v2.
- Ports 5000, 9090, and 3000 available.
- Git for the GitHub upload steps.

You do not need Python installed to run the Docker stack. Python 3.10+ is needed for local development, the scenario simulator, and the smoke script.

## First-time setup and run with Docker (recommended)

Open PowerShell in the project directory:

~~~powershell
Set-Location 'C:\Users\laksh\Downloads\crypto_proj'
~~~

Create a private local environment file from the template if one does not exist:

~~~powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
~~~

Set HMAC_SECRET_KEY to a new random value. Generate one with:

~~~powershell
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$bytes = New-Object byte[] 32
$rng.GetBytes($bytes)
[BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
$rng.Dispose()
~~~

Copy the generated value into .env. Set GRAFANA_ADMIN_PASSWORD to a private password. Change the demo login values if you intend to use the login scenario. Never commit .env. The checked-in .env.example is a template and must not contain real credentials.

Check Docker and Compose, then build and start:

~~~powershell
docker version
docker compose version
docker compose config --quiet
docker compose up --build -d
docker compose ps
~~~

Wait for flask-app to report healthy and the other services to show Up. The first run downloads the Python, Prometheus, and Grafana images.

Open the services:

| Service | Address | Purpose |
| --- | --- | --- |
| Flask demo | http://localhost:5000 | Application routes and scenarios. |
| Prometheus | http://localhost:9090 | Metrics queries. |
| Prometheus targets | http://localhost:9090/targets | Confirm the cybersentinel target is UP. |
| Grafana | http://localhost:3000 | Dashboard, sign in as admin with GRAFANA_ADMIN_PASSWORD. |
| Dashboard | http://localhost:3000/d/cybersentinel | Runtime security and anomaly metrics. |

Select a time range such as Last 15 minutes and a 10-second refresh in Grafana. The detector's trained score can take a few minutes to appear.

## Trigger scenarios

With Docker running, use a browser or PowerShell. These routes trigger one observation each:

~~~powershell
Invoke-RestMethod http://localhost:5000/
Invoke-RestMethod http://localhost:5000/api/data
Invoke-RestMethod -Method Post http://localhost:5000/login -ContentType 'application/json' -Body '{"username":"admin","password":"wrong"}'
Invoke-RestMethod http://localhost:5000/admin
Invoke-RestMethod http://localhost:5000/admin -Headers @{ 'X-Auth-Token' = 'demo-token-abc123' }
Invoke-RestMethod http://localhost:5000/error
Invoke-RestMethod http://localhost:5000/slow
Invoke-WebRequest http://localhost:5000/metrics
~~~

Expected effects:

| Scenario | Effect |
| --- | --- |
| Normal requests | Request count and latency observations increase. |
| Failed login | HTTP 401, failed-login and security-event counters rise. |
| Unauthorized admin request | HTTP 403, unauthorized and security-event counters rise. |
| High request volume | Request rate increases; use simulator option 4. |
| Application error | /error intentionally returns HTTP 500 and increments error/security metrics. |
| Slow response | /slow waits about two seconds and raises the latency histogram. |

The scenario simulator uses only Python's standard library. If Python is installed, run this from a second terminal:

~~~powershell
python simulate_scenarios.py
~~~

Choose options 1-6, or 0 to run all scenarios. The script targets localhost:5000, which is exposed by Docker Compose.

## Verify the app

The smoke script checks ten route and metrics behaviors against a running app. It includes a two-second slow request.

~~~powershell
python test_phase1.py
~~~

For local development without Docker, install Python 3.10+, create a virtual environment, install requirements, create .env as above, and run:

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m app.main
~~~

In another terminal with the same virtual environment activated, run test_phase1.py or simulate_scenarios.py. Prometheus and Grafana need to be started separately for this local-only app mode.

## Stop and reopen

Stop the Docker stack but preserve its named volumes:

~~~powershell
docker compose down
~~~

When reopening the project, start Docker Desktop, return to this folder, and run:

~~~powershell
docker compose up -d
docker compose ps
~~~

Use docker compose up --build -d after changing the app or dependencies. View logs with docker compose logs -f flask-app, docker compose logs -f prometheus, or docker compose logs -f grafana. Named volumes preserve Prometheus and Grafana state. To delete that state as well as the containers, run docker compose down -v.

The optional native Windows scripts start Flask, a separately downloaded Prometheus, and a separately downloaded Grafana in individual windows. They depend on third-party binaries under tools/, which is intentionally excluded from GitHub. A fresh clone should use Docker; the native scripts are for a local tools installation.

## Repository contents

~~~text
app/                         Flask routes, metrics, configuration, HMAC helpers
ml/                          Metric features and Isolation Forest detector
prometheus/prometheus.yml    Native Windows scrape configuration
prometheus/prometheus.docker.yml
                             Docker network scrape configuration
grafana/dashboards/          Dashboard JSON
grafana/provisioning/        Native Windows Grafana provisioning
grafana/provisioning/docker/ Docker-specific Grafana provisioning
simulate_scenarios.py        Interactive scenario generator
test_phase1.py               Manual route/metrics smoke script
docker-compose.yml           Flask, Prometheus, and Grafana services
start_all.ps1 / stop_all.ps1  Optional native Windows launch/stop scripts
~~~

