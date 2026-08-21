<#
Starts the Text-to-SQL API (FastAPI/uvicorn) and the Streamlit UI together,
each in its own PowerShell window so you can watch their logs and Ctrl+C
them independently.

Usage (from the repo root):
    .\start.ps1

If PowerShell blocks the script with an execution-policy error, run once:
    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#>

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

# --- .env check ----------------------------------------------------------

if (-not (Test-Path ".env")) {
    Write-Host "No .env file found in $RepoRoot." -ForegroundColor Red
    Write-Host "Create one first -- see README.md 'Prerequisites & Setup' for the required keys (DB_*, GROQ_API_KEY)." -ForegroundColor Yellow
    exit 1
}

# --- Read API_HOST / API_PORT / API_BASE_URL from .env (app/config.py's own defaults if absent) ---

$envContent = Get-Content ".env" -Raw

function Get-EnvValue($name, $default) {
    if ($envContent -match "(?m)^\s*$name\s*=\s*(.+?)\s*$") {
        return $Matches[1].Trim('"').Trim("'")
    }
    return $default
}

$ApiHost = Get-EnvValue "API_HOST" "127.0.0.1"
$ApiPort = Get-EnvValue "API_PORT" "8000"
$ApiBaseUrl = Get-EnvValue "API_BASE_URL" "http://${ApiHost}:${ApiPort}"

# --- Optional virtualenv activation (this project normally uses the system Python, but pick one up if present) ---

$VenvActivate = $null
foreach ($candidate in @(".venv\Scripts\Activate.ps1", "venv\Scripts\Activate.ps1")) {
    if (Test-Path $candidate) { $VenvActivate = $candidate; break }
}
if ($VenvActivate) {
    Write-Host "Found virtualenv activation script: $VenvActivate (will activate it in each window)" -ForegroundColor Cyan
}

# --- Start the API in its own window --------------------------------------

Write-Host "Starting API on http://${ApiHost}:${ApiPort} ..." -ForegroundColor Cyan

$apiCommand = "uvicorn app.main:app --host $ApiHost --port $ApiPort --reload"
if ($VenvActivate) { $apiCommand = "& '$VenvActivate'; $apiCommand" }

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$RepoRoot'; $apiCommand" -WindowStyle Normal

# --- Wait for the API health endpoint before starting the UI --------------

Write-Host "Waiting for the API to become healthy (loads the embedding + reranker models, can take ~10-20s)..." -ForegroundColor Cyan

$healthUrl = "$ApiBaseUrl/api/v1/health"
$ready = $false

for ($i = 0; $i -lt 60; $i++) {
    try {
        $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
        if ($response.status -eq "ok") { $ready = $true; break }
    } catch {
        # API not up yet (or still loading models) -- keep polling
    }
    Start-Sleep -Seconds 2
}

if ($ready) {
    Write-Host "API is healthy." -ForegroundColor Green
} else {
    Write-Host "API did not report healthy within the timeout -- check its window for errors." -ForegroundColor Red
    Write-Host "Continuing to start the UI anyway; it may show connection errors until the API is up." -ForegroundColor Yellow
}

# --- Start the Streamlit UI in its own window ------------------------------

Write-Host "Starting Streamlit UI..." -ForegroundColor Cyan

$uiCommand = "streamlit run ui\streamlit_app.py"
if ($VenvActivate) { $uiCommand = "& '$VenvActivate'; $uiCommand" }

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$RepoRoot'; $uiCommand" -WindowStyle Normal

Write-Host ""
Write-Host "Started:" -ForegroundColor Green
Write-Host "  API:  $ApiBaseUrl  (Swagger docs at $ApiBaseUrl/docs)"
Write-Host "  UI:   http://localhost:8501  (opens automatically in your browser)"
Write-Host ""
Write-Host "Each service runs in its own PowerShell window -- close the window or press Ctrl+C in it to stop that service." -ForegroundColor DarkGray
