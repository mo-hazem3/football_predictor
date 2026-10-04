<#
.SYNOPSIS
  Start Football comps locally: the Django API (http://127.0.0.1:8000) and the web app (http://127.0.0.1:5173).

.DESCRIPTION
  Checks the prerequisites, builds the model cache if it is missing, opens the API and the web app in two
  windows (so you can see their logs), waits until both answer, and opens the browser.

  .\start.cmd                 start everything and open the browser
  .\start.cmd -NoBrowser      same, without opening the browser
  .\start.cmd -BuildCache     rebuild the model cache first (about 2 minutes; do this after rebuilding the data)
  .\start.cmd -Stop           stop what this script started

  start.cmd just calls this script with the execution policy bypassed for that one run, so it works
  on a default Windows install; run start.ps1 directly if your policy already allows scripts.
#>
param(
    [switch]$NoBrowser,
    [switch]$BuildCache,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Database = Join-Path $Root "data\db\football.sqlite"
$Cache = Join-Path $Root "data\cache\forecaster.pkl"
$PortableNode = Join-Path $Root ".tools\node-v24.21.0-win-x64"
$PidFile = Join-Path $Root ".tools\start.pids"
$ApiUrl = "http://127.0.0.1:8000"
$WebUrl = "http://127.0.0.1:5173"

function Test-Up([string]$Url) {
    try { $null = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3; return $true } catch { return $false }
}

function Wait-Up([string]$Url, [string]$What, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Up $Url) { return }
        Start-Sleep -Milliseconds 700
    }
    throw "$What did not come up within $Seconds seconds. Look at its window for the error."
}

# ---------------------------------------------------------------- stop
if ($Stop) {
    if (Test-Path $PidFile) {
        foreach ($id in Get-Content $PidFile) {
            if ($id) { cmd /c "taskkill /PID $id /T /F >nul 2>&1" }
        }
        Remove-Item $PidFile -Force
    }
    # anything of ours still holding the ports (only processes that are clearly this app's servers)
    foreach ($port in 8000, 5173) {
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)" -ErrorAction SilentlyContinue
            if ($proc -and $proc.CommandLine -match "manage\.py runserver|vite") { Stop-Process -Id $proc.ProcessId -Force }
        }
    }
    Write-Host "Stopped."
    return
}

# ---------------------------------------------------------------- prerequisites
if (-not (Test-Path $Python)) {
    throw "Python environment not found ($Python). Create it from the project folder with:  py -m venv .venv ; .\.venv\Scripts\pip install -e "".[dev]"""
}
if (-not (Test-Path $Database)) {
    throw "No pipeline database at $Database. Build the data first (see 'Quick start' in README.md)."
}

# Node 20.19+ is needed by Vite. Prefer the project's portable copy; otherwise accept a recent system Node.
$NodeDir = ""
if (Test-Path (Join-Path $PortableNode "node.exe")) {
    $NodeDir = $PortableNode
} else {
    $version = $null
    try { $version = (& node --version) } catch { }
    if (-not $version -or [int](($version -replace "^v(\d+)\..*", '$1')) -lt 20) {
        throw "Node 20.19 or newer is required (found: $version). Install the current LTS from https://nodejs.org, or restore .tools\node-v24.21.0-win-x64."
    }
}
if ($NodeDir) { $env:Path = "$NodeDir;$env:Path" }

if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    Write-Host "Installing frontend packages (first run only)..."
    Push-Location $Frontend
    try { & npm ci } finally { Pop-Location }
}

if ($BuildCache -or -not (Test-Path $Cache)) {
    Write-Host "Building the model cache (about 2 minutes)..."
    Push-Location $Backend
    try { $env:DJANGO_DEBUG = "1"; & $Python manage.py build_forecast_cache } finally { Pop-Location }
}

# ---------------------------------------------------------------- start
$started = @()
New-Item -ItemType Directory -Force -Path (Split-Path $PidFile) | Out-Null

if (Test-Up "$ApiUrl/api/v1/health/") {
    Write-Host "The API is already running on :8000 - reusing it."
} else {
    $apiCommand = "`$host.UI.RawUI.WindowTitle = 'Football comps API (:8000)'; `$env:DJANGO_DEBUG = '1'; & '$Python' manage.py runserver 127.0.0.1:8000 --noreload"
    $api = Start-Process powershell -ArgumentList "-NoExit -NoProfile -Command `"$apiCommand`"" -WorkingDirectory $Backend -PassThru
    $started += $api.Id
}

if (Test-Up $WebUrl) {
    Write-Host "The web app is already running on :5173 - reusing it."
} else {
    $nodePrefix = if ($NodeDir) { "`$env:Path = '$NodeDir;' + `$env:Path; " } else { "" }
    $webCommand = "`$host.UI.RawUI.WindowTitle = 'Football comps web (:5173)'; ${nodePrefix}npm run dev -- --host 127.0.0.1"
    $web = Start-Process powershell -ArgumentList "-NoExit -NoProfile -Command `"$webCommand`"" -WorkingDirectory $Frontend -PassThru
    $started += $web.Id
}
if ($started.Count) { $started | Set-Content $PidFile }

Write-Host "Waiting for the API..."
Wait-Up "$ApiUrl/api/v1/health/" "The API" 60
Write-Host "Loading the models (a few seconds; about 2 minutes if the cache had to be rebuilt)..."
$null = Invoke-WebRequest -Uri "$ApiUrl/api/v1/meta/" -UseBasicParsing -TimeoutSec 300
Write-Host "Waiting for the web app..."
Wait-Up $WebUrl "The web app" 90

Write-Host ""
Write-Host "Ready."
Write-Host "  App        $WebUrl"
Write-Host "  API docs   $ApiUrl/api/docs/"
Write-Host "  Stop with  .\start.cmd -Stop   (or close the two windows)"
if (-not $NoBrowser) { Start-Process $WebUrl }
