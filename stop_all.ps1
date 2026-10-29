# stop_all.ps1
# Stops all CyberSentinel services.

Write-Host ""
Write-Host "  Stopping CyberSentinel services..." -ForegroundColor Yellow

$stopped = 0

# Stop Flask (python processes running app.main)
Get-Process -Name "python" -ErrorAction SilentlyContinue | ForEach-Object {
    $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)" -ErrorAction SilentlyContinue).CommandLine
    if ($cmdLine -match "app\.main") {
        Stop-Process -Id $_.Id -Force
        Write-Host "  [x] Flask app stopped (PID $($_.Id))" -ForegroundColor Red
        $stopped++
    }
}

# Stop Prometheus
Get-Process -Name "prometheus" -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.Id -Force
    Write-Host "  [x] Prometheus stopped (PID $($_.Id))" -ForegroundColor Red
    $stopped++
}

# Stop Grafana
Get-Process -Name "grafana-server" -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.Id -Force
    Write-Host "  [x] Grafana stopped (PID $($_.Id))" -ForegroundColor Red
    $stopped++
}

if ($stopped -eq 0) {
    Write-Host "  No CyberSentinel services were running." -ForegroundColor DarkGray
} else {
    Write-Host "  $stopped service(s) stopped." -ForegroundColor Green
}
Write-Host ""
