<#
  Fulyn launcher: one click from the Start menu or desktop.

  Shows a small "Starting Fulyn" window, then:
    1. starts Docker Desktop if the Docker engine isn't running,
    2. starts Ollama if it isn't running (Fulyn still opens without it),
    3. brings up the production containers (builds only what changed),
    4. waits until the app is healthy,
    5. opens Fulyn in its own app window (Edge, else Chrome, else the default browser).

  If Fulyn is already running it opens immediately.
  Logs: launcher\logs\launcher.log (no personal data is written there).
#>

# Failures are checked explicitly; "Stop" would turn docker's normal stderr output into errors.
$ErrorActionPreference = "Continue"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $PSScriptRoot "logs"
$Log = Join-Path $LogDir "launcher.log"
$AppUrl = "http://localhost:3000/"
$HealthUrl = "http://127.0.0.1:3000/api/health"
$OllamaUrl = "http://127.0.0.1:11434/api/version"
$ComposeArgs = @("compose", "-f", "docker-compose.yml", "-f", "docker-compose.prod.yml")

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
function Write-Log([string]$Message) {
    Add-Content -Path $Log -Value ("{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message)
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

# --- Splash window -------------------------------------------------------------

$Splash = New-Object System.Windows.Forms.Form
$Splash.Text = "Fulyn"
$Splash.Icon = New-Object System.Drawing.Icon (Join-Path $PSScriptRoot "fulyn.ico")
$Splash.FormBorderStyle = "None"
$Splash.StartPosition = "CenterScreen"
$Splash.Size = New-Object System.Drawing.Size(360, 150)
$Splash.BackColor = [System.Drawing.ColorTranslator]::FromHtml("#0e1420")
$Splash.TopMost = $true
$Splash.ShowInTaskbar = $true

$Logo = New-Object System.Windows.Forms.PictureBox
$Logo.Image = (New-Object System.Drawing.Icon((Join-Path $PSScriptRoot "fulyn.ico"), 64, 64)).ToBitmap()
$Logo.SizeMode = "Zoom"
$Logo.Location = New-Object System.Drawing.Point(24, 43)
$Logo.Size = New-Object System.Drawing.Size(64, 64)
$Splash.Controls.Add($Logo)

$Title = New-Object System.Windows.Forms.Label
$Title.Text = "Fulyn"
$Title.ForeColor = [System.Drawing.Color]::White
$Title.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 16)
$Title.Location = New-Object System.Drawing.Point(104, 42)
$Title.AutoSize = $true
$Splash.Controls.Add($Title)

$Status = New-Object System.Windows.Forms.Label
$Status.Text = "Starting..."
$Status.ForeColor = [System.Drawing.ColorTranslator]::FromHtml("#9aa7c2")
$Status.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$Status.Location = New-Object System.Drawing.Point(106, 80)
$Status.Size = New-Object System.Drawing.Size(240, 40)
$Splash.Controls.Add($Status)

function Set-Status([string]$Text) {
    $Status.Text = $Text
    Write-Log $Text
    [System.Windows.Forms.Application]::DoEvents()
}

function Pump([int]$Milliseconds) {
    $until = (Get-Date).AddMilliseconds($Milliseconds)
    while ((Get-Date) -lt $until) {
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 100
    }
}

function Fail([string]$Message) {
    Write-Log "ERROR: $Message"
    $Splash.Hide()
    [System.Windows.Forms.MessageBox]::Show(
        "$Message`n`nDetails: $Log", "Fulyn could not start", "OK", "Error"
    ) | Out-Null
    exit 1
}

# --- Checks ------------------------------------------------------------------------

function Test-Url([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-FulynHealthy {
    try {
        $health = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 3
        return $health.status -eq "ok"
    } catch {
        return $false
    }
}

function Test-Docker {
    & docker info --format "{{.ServerVersion}}" *> $null
    return $LASTEXITCODE -eq 0
}

function Wait-Until([scriptblock]$Condition, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Condition) { return $true }
        Pump 1000
    }
    return $false
}

# --- Open the app window -----------------------------------------------------------

function Open-App {
    $browsers = @(
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    foreach ($browser in $browsers) {
        if ($browser -and (Test-Path $browser)) {
            # --app gives Fulyn its own window, without tabs or an address bar.
            Start-Process -FilePath $browser -ArgumentList "--app=$AppUrl"
            return
        }
    }
    Start-Process $AppUrl
}

# --- Main --------------------------------------------------------------------------

Write-Log "---- launch ----"

# Fast path: already running.
if (Test-FulynHealthy) {
    Write-Log "Already running"
    Open-App
    exit 0
}

$Splash.Show()
[System.Windows.Forms.Application]::DoEvents()

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "Docker is not installed or not on PATH. Install Docker Desktop, then try again."
}

if (-not (Test-Docker)) {
    Set-Status "Starting Docker..."
    $dockerDesktop = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path $dockerDesktop)) {
        Fail "Docker Desktop was not found at `"$dockerDesktop`". Start it manually, then try again."
    }
    Start-Process -FilePath $dockerDesktop
    if (-not (Wait-Until { Test-Docker } 240)) {
        Fail "Docker did not start within 4 minutes."
    }
}

if (-not (Test-Url $OllamaUrl)) {
    Set-Status "Starting Ollama..."
    $ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe"
    if (Test-Path $ollama) {
        Start-Process -FilePath $ollama
        if (-not (Wait-Until { Test-Url $OllamaUrl } 45)) {
            Write-Log "Ollama did not respond; continuing without it"
        }
    } else {
        Write-Log "Ollama not found; chat and memory search will be unavailable"
    }
}

Set-Status "Starting Fulyn..."
$composeLog = Join-Path $LogDir "compose.log"
$compose = Start-Process -FilePath "docker" -ArgumentList ($ComposeArgs + @("up", "-d", "--build")) `
    -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $composeLog -RedirectStandardError "$composeLog.err"
# Read the handle now: Windows PowerShell only reports ExitCode if it was cached early.
$null = $compose.Handle
$started = Get-Date
while (-not $compose.HasExited) {
    if (((Get-Date) - $started).TotalSeconds -gt 20) {
        $Status.Text = "Preparing Fulyn (first start or after an update can take a few minutes)..."
    }
    Pump 500
}
if ($compose.ExitCode -ne 0) {
    Fail "The containers failed to start (docker compose exit code $($compose.ExitCode)). See $composeLog.err"
}

Set-Status "Almost ready..."
if (-not (Wait-Until { Test-FulynHealthy } 180)) {
    Fail "Fulyn started but did not become healthy within 3 minutes."
}

if (-not (Test-Url $OllamaUrl)) {
    Set-Status "Ollama is not running: chat will be unavailable."
    Pump 2500
}

Write-Log "Ready"
Open-App
Pump 1500
$Splash.Close()
