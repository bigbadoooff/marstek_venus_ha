<#
.SYNOPSIS
    Deploys Home Assistant custom integrations to an HA instance via a network share.

.DESCRIPTION
    Copies every subdirectory found under custom_components\ to the HA custom_components
    folder on the network share, then optionally restarts Home Assistant via the REST API.

    Only the integration folders present in this repo are touched; other integrations
    already on the HA share are left untouched.

    Configuration is loaded from deploy.config.ps1 (gitignored). Copy deploy.config.ps1.example
    and fill in your values before first use.

.PARAMETER ConfigFile
    Path to the config file. Defaults to deploy.config.ps1 in the same directory as this script.

.PARAMETER SkipRestart
    If set, skips restarting Home Assistant after deploying.

.PARAMETER RunTests
    If set, runs pytest before deploying. Aborts on test failure.

.EXAMPLE
    .\deploy.ps1
    .\deploy.ps1 -SkipRestart
    .\deploy.ps1 -RunTests
#>
[CmdletBinding()]
param(
    [string]$ConfigFile = "$PSScriptRoot\deploy.config.ps1",
    [switch]$SkipRestart,
    [switch]$RunTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Load config ──────────────────────────────────────────────────────────────
if (-not (Test-Path $ConfigFile)) {
    Write-Error "Config file not found: $ConfigFile`nCopy deploy.config.ps1.example to deploy.config.ps1 and fill in your values."
    exit 1
}
. $ConfigFile

# Expected variables set by config:
#   $HA_SHARE_PATH    UNC path to the custom_components folder
#                     e.g. "\\\\LOXBERRY2\\Home Assistant\\custom_components"
#   $HA_API_URL       HA base URL for REST API restart (optional)
#                     e.g. "http://homeassistant.local:8123"
#   $HA_TOKEN         Long-lived access token for the REST API (optional)

foreach ($var in @("HA_SHARE_PATH")) {
    if (-not (Get-Variable -Name $var -ErrorAction SilentlyContinue)) {
        Write-Error "Missing required config variable: `$$var"
        exit 1
    }
}

$CustomComponentsDir = "$PSScriptRoot\custom_components"

# ── Optional: run tests ───────────────────────────────────────────────────────
if ($RunTests) {
    Write-Host "Running tests..." -ForegroundColor Cyan
    pytest "$PSScriptRoot\tests" --tb=short -q
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Tests failed. Aborting deployment."
        exit 1
    }
    Write-Host "Tests passed." -ForegroundColor Green
}

# ── Deploy ────────────────────────────────────────────────────────────────────
if (-not (Test-Path $HA_SHARE_PATH)) {
    Write-Error "Network share not reachable: $HA_SHARE_PATH"
    exit 1
}

$integrations = @(Get-ChildItem $CustomComponentsDir -Directory)
if ($integrations.Count -eq 0) {
    Write-Error "No integration folders found under: $CustomComponentsDir"
    exit 1
}

$anyFailed = $false
foreach ($integration in $integrations) {
    $DstDir = Join-Path $HA_SHARE_PATH $integration.Name
    Write-Host "Deploying $($integration.Name) -> $DstDir" -ForegroundColor Cyan
    # /MIR mirrors this integration only; other integrations on the share are untouched.
    # Exit codes 0-7 are success (bitmask: 1=copied, 2=extra removed, 4=mismatched)
    robocopy $integration.FullName $DstDir /MIR /XD __pycache__ /XF *.pyc /NFL /NDL /NJH
    if ($LASTEXITCODE -gt 7) {
        Write-Warning "robocopy failed for $($integration.Name) (exit code $LASTEXITCODE)"
        $anyFailed = $true
    }
}

if ($anyFailed) {
    Write-Error "One or more integrations failed to deploy."
    exit 1
}

Write-Host "All integrations deployed successfully." -ForegroundColor Green

# ── Restart HA via REST API ───────────────────────────────────────────────────
if (-not $SkipRestart) {
    $apiUrl   = (Get-Variable -Name "HA_API_URL" -ErrorAction SilentlyContinue).Value
    $haToken  = (Get-Variable -Name "HA_TOKEN"   -ErrorAction SilentlyContinue).Value

    if ($apiUrl -and $haToken) {
        Write-Host "Restarting Home Assistant via REST API..." -ForegroundColor Cyan
        $headers = @{ Authorization = "Bearer $haToken"; "Content-Type" = "application/json" }
        try {
            Invoke-RestMethod -Uri "$apiUrl/api/services/homeassistant/restart" `
                              -Method Post -Headers $headers -Body "{}" | Out-Null
            Write-Host "Home Assistant restart triggered." -ForegroundColor Green
        } catch {
            Write-Warning "REST API restart failed: $_"
            Write-Warning "Restart Home Assistant manually via the UI."
        }
    } else {
        Write-Host "HA_API_URL / HA_TOKEN not set - restart Home Assistant manually via the UI." -ForegroundColor Yellow
    }
} else {
    Write-Host "Skipping restart (-SkipRestart was set)." -ForegroundColor Yellow
}

Write-Host "`nDone." -ForegroundColor Green
