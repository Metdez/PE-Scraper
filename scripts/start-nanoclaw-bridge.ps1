$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$stateDir = Join-Path $env:LOCALAPPDATA "PE-Scraper"
$tokenFile = Join-Path $stateDir "nanoclaw-bridge.token"
$stdoutLog = Join-Path $stateDir "nanoclaw-bridge.stdout.log"
$stderrLog = Join-Path $stateDir "nanoclaw-bridge.stderr.log"

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8765/healthz" -TimeoutSec 2
    if ($health.status -eq "ok") {
        exit 0
    }
} catch {
    # The bridge is not running yet.
}

$uv = (Get-Command uv -ErrorAction Stop).Source
$arguments = "run python scripts\nanoclaw_bridge.py --token-file `"$tokenFile`""

Start-Process `
    -FilePath $uv `
    -ArgumentList $arguments `
    -WorkingDirectory $projectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog
