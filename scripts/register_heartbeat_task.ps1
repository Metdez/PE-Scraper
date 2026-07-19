# Registers a Windows Task Scheduler task that runs `pescraper heartbeat` daily.
# Not run automatically by the pipeline — a one-time, explicit opt-in step.
#
# Usage (from an elevated or normal PowerShell prompt, from the repo root):
#   .\scripts\register_heartbeat_task.ps1
#
# The heartbeat itself is a zero-cost no-op when the queue is empty and no
# firm is stale (worker.run_heartbeat's script-gate), so a daily schedule is
# safe to leave running unattended.

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pescraperExe = Join-Path $repoRoot ".venv\Scripts\pescraper.exe"

if (-not (Test-Path $pescraperExe)) {
    throw "pescraper.exe not found at $pescraperExe — run 'uv sync' first."
}

$action = New-ScheduledTaskAction -Execute $pescraperExe -Argument "heartbeat" -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -Daily -At 2am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd

Register-ScheduledTask -TaskName "PEScraperHeartbeat" `
    -Action $action -Trigger $trigger -Settings $settings `
    -Description "Runs pescraper heartbeat: processes queued/stale firms, no-ops if there's no work." `
    -Force

Write-Host "Registered scheduled task 'PEScraperHeartbeat' (daily at 2am)."
Write-Host "View/manage it in Task Scheduler, or run: Get-ScheduledTask -TaskName PEScraperHeartbeat"
