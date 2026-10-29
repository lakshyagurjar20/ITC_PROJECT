# start_all.ps1
# ============================================================
# CyberSentinel — One-command startup (no Docker needed)
#
# Starts three services in separate windows:
#   1. Flask app    on http://localhost:5000
#   2. Prometheus   on http://localhost:9090
#   3. Grafana      on http://localhost:3000
#
# Usage:
#   .\start_all.ps1
#
# To stop everything:
#   .\stop_all.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$PROJECT_ROOT = $PSScriptRoot
if (-not $PROJECT_ROOT) { $PROJECT_ROOT = Get-Location }

$PROMETHEUS_DIR = Join-Path $PROJECT_ROOT "tools\prometheus-2.51.2.windows-amd64"
$GRAFANA_DIR    = Join-Path $PROJECT_ROOT "tools\grafana-v10.4.2"
$PROM_EXE       = Join-Path $PROMETHEUS_DIR "prometheus.exe"
$GRAFANA_BIN    = Join-Path $GRAFANA_DIR "bin\grafana-server.exe"

# --- Validation ---
if (-not (Test-Path $PROM_EXE)) {
    Write-Host "[ERROR] Prometheus not found at: $PROM_EXE" -ForegroundColor Red
    Write-Host "        Run the extraction step first. See README.md." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $GRAFANA_BIN)) {
    # Try alternate dir name
    $GRAFANA_DIR = Get-ChildItem -Path (Join-Path $PROJECT_ROOT "tools") -Directory -Filter "grafana-*" | Select-Object -First 1 -ExpandProperty FullName
    if ($GRAFANA_DIR) { $GRAFANA_BIN = Join-Path $GRAFANA_DIR "bin\grafana-server.exe" }
    if (-not (Test-Path $GRAFANA_BIN)) {
        Write-Host "[ERROR] Grafana not found." -ForegroundColor Red
        Write-Host "        Run the extraction step first. See README.md." -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  CyberSentinel — Starting All Services" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# --- 1. Flask App ---
Write-Host "  [1/3] Starting Flask app..." -ForegroundColor Green
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$PROJECT_ROOT'; `$host.UI.RawUI.WindowTitle = 'CyberSentinel - Flask App'; python -m app.main"
)

Start-Sleep -Seconds 3

# --- 2. Prometheus ---
Write-Host "  [2/3] Starting Prometheus..." -ForegroundColor Green
$promConfigPath = Join-Path $PROJECT_ROOT "prometheus\prometheus.yml"
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "`$host.UI.RawUI.WindowTitle = 'CyberSentinel - Prometheus'; & '$PROM_EXE' --config.file='$promConfigPath' --storage.tsdb.path='$PROJECT_ROOT\tools\prometheus_data' --storage.tsdb.retention.time=7d --web.listen-address=0.0.0.0:9090"
)

Start-Sleep -Seconds 2

# --- 3. Grafana ---
Write-Host "  [3/3] Starting Grafana..." -ForegroundColor Green
# Copy provisioning files into Grafana's conf directory
$grafanaProvDir = Join-Path $GRAFANA_DIR "conf\provisioning"
if (Test-Path (Join-Path $PROJECT_ROOT "grafana\provisioning")) {
    Copy-Item -Recurse -Force (Join-Path $PROJECT_ROOT "grafana\provisioning\datasources") (Join-Path $grafanaProvDir "datasources")
    Copy-Item -Recurse -Force (Join-Path $PROJECT_ROOT "grafana\provisioning\dashboards") (Join-Path $grafanaProvDir "dashboards")
}
# Copy dashboard JSON into Grafana's data/dashboards folder
$grafanaDashDir = Join-Path $GRAFANA_DIR "data\dashboards"
New-Item -ItemType Directory -Path $grafanaDashDir -Force | Out-Null
Copy-Item -Force (Join-Path $PROJECT_ROOT "grafana\dashboards\cybersentinel.json") $grafanaDashDir

# Update dashboard provider to use the correct path
$providerYml = Join-Path $grafanaProvDir "dashboards\dashboard-provider.yml"
$provContent = @"
apiVersion: 1
providers:
  - name: CyberSentinel
    orgId: 1
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: $grafanaDashDir
      foldersFromFilesStructure: false
"@
$provContent | Set-Content -Path $providerYml -Encoding UTF8

Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$GRAFANA_DIR'; `$host.UI.RawUI.WindowTitle = 'CyberSentinel - Grafana'; & '.\bin\grafana-server.exe'"
)

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  All services started!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Flask app  : http://localhost:5000" -ForegroundColor White
Write-Host "  Prometheus : http://localhost:9090" -ForegroundColor White
Write-Host "  Grafana    : http://localhost:3000  (admin / admin)" -ForegroundColor White
Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "  Dashboard  : http://localhost:3000/d/cybersentinel" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  To run scenarios:  python simulate_scenarios.py" -ForegroundColor DarkGray
Write-Host "  To stop all:       .\stop_all.ps1" -ForegroundColor DarkGray
Write-Host ""
