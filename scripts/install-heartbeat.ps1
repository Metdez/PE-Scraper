param(
    [string]$TaskName = "PE Scraper Heartbeat",
    [int]$EveryMinutes = 15
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Uv = (Get-Command uv -ErrorAction Stop).Source
$Command = "Set-Location -LiteralPath '$ProjectRoot'; & '$Uv' run pescraper heartbeat"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -NonInteractive -Command `"$Command`""
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Description "Runs PE Scraper queued and stale-firm heartbeat." -Force | Out-Null
Write-Output "Installed scheduled task '$TaskName' every $EveryMinutes minutes."
