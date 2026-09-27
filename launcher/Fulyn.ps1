<#
  Fulyn startup steps:
    1. start Docker Desktop if the Docker engine isn't running,
    2. start Ollama if it isn't running (Fulyn still opens without it),
    3. bring up the production containers (building only what changed),
    4. wait until the app is healthy.

  Modes:
    -Prepare   Used by Fulyn.exe. No UI: prints "STATUS: ..." / "ERROR: ..." lines and exits
               0 when Fulyn is ready, 1 on failure. Fulyn.exe shows the window.
    (default)  Fallback without Fulyn.exe: shows a small splash window, then opens Fulyn in an
               Edge/Chrome app window.

  Logs: launcher\logs\launcher.log (no personal data is written there).
#>

param([switch]$Prepare)

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

# --- Progress reporting: stdout lines (-Prepare) or a splash window ----------------

$Splash = $null
$StatusLabel = $null

function Show-Splash {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    [System.Windows.Forms.Application]::EnableVisualStyles()
    $icon = Join-Path $PSScriptRoot "fulyn.ico"

    $form = New-Object System.Windows.Forms.Form
    $form.Text = "Fulyn"
    $form.Icon = New-Object System.Drawing.Icon $icon
    $form.FormBorderStyle = "None"
    $form.StartPosition = "CenterScreen"
    $form.Size = New-Object System.Drawing.Size(360, 150)
    $form.BackColor = [System.Drawing.ColorTranslator]::FromHtml("#0e1420")
    $form.TopMost = $true

    $logo = New-Object System.Windows.Forms.PictureBox
    $logo.Image = (New-Object System.Drawing.Icon($icon, 64, 64)).ToBitmap()
    $logo.SizeMode = "Zoom"
    $logo.Location = New-Object System.Drawing.Point(24, 43)
    $logo.Size = New-Object System.Drawing.Size(64, 64)
    $form.Controls.Add($logo)

    $title = New-Object System.Windows.Forms.Label
    $title.Text = "Fulyn"
    $title.ForeColor = [System.Drawing.Color]::White
    $title.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 16)
    $title.Location = New-Object System.Drawing.Point(104, 42)
    $title.AutoSize = $true
    $form.Controls.Add($title)

    $label = New-Object System.Windows.Forms.Label
    $label.Text = "Starting..."
    $label.ForeColor = [System.Drawing.ColorTranslator]::FromHtml("#9aa7c2")
    $label.Font = New-Object System.Drawing.Font("Segoe UI", 10)
    $label.Location = New-Object System.Drawing.Point(106, 80)
    $label.Size = New-Object System.Drawing.Size(240, 40)
    $form.Controls.Add($label)

    $form.Show()
    [System.Windows.Forms.Application]::DoEvents()
    $script:Splash = $form
    $script:StatusLabel = $label
}

function Set-Status([string]$Text) {
    Write-Log $Text
    if ($Prepare) {
        [Console]::Out.WriteLine("STATUS: $Text")
        [Console]::Out.Flush()
    } elseif ($StatusLabel) {
        $StatusLabel.Text = $Text
        [System.Windows.Forms.Application]::DoEvents()
    }
}

function Pump([int]$Milliseconds) {
    if ($Prepare -or -not $Splash) {
        Start-Sleep -Milliseconds $Milliseconds
        return
    }
    $until = (Get-Date).AddMilliseconds($Milliseconds)
    while ((Get-Date) -lt $until) {
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 100
    }
}

function Fail([string]$Message) {
    Write-Log "ERROR: $Message"
    if ($Prepare) {
        [Console]::Out.WriteLine("ERROR: $Message")
        [Console]::Out.Flush()
    } else {
        if ($Splash) { $Splash.Hide() }
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            "$Message`n`nDetails: $Log", "Fulyn could not start", "OK", "Error"
        ) | Out-Null
    }
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

function Open-InBrowser {
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

Write-Log ("---- launch ({0}) ----" -f $(if ($Prepare) { "app" } else { "browser" }))

if (Test-FulynHealthy) {
    Write-Log "Already running"
    if (-not $Prepare) { Open-InBrowser }
    exit 0
}

if (-not $Prepare) { Show-Splash }

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "Docker is not installed or not on PATH. Install Docker Desktop, then try again."
}

if (-not (Test-Docker)) {
    Set-Status "Starting Docker..."
    $dockerDesktop = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path $dockerDesktop)) {
        Fail "Docker Desktop was not found. Start it manually, then try again."
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
$slowShown = $false
while (-not $compose.HasExited) {
    if (-not $slowShown -and ((Get-Date) - $started).TotalSeconds -gt 20) {
        Set-Status "Preparing Fulyn. The first start, or the first after an update, takes a few minutes..."
        $slowShown = $true
    }
    Pump 500
}
if ($compose.ExitCode -ne 0) {
    Fail "The containers failed to start (docker compose exit code $($compose.ExitCode)). See logs\compose.log.err"
}

Set-Status "Almost ready..."
if (-not (Wait-Until { Test-FulynHealthy } 180)) {
    Fail "Fulyn started but did not become healthy within 3 minutes."
}

if (-not (Test-Url $OllamaUrl)) {
    Set-Status "Ollama is not running, so chat will be unavailable."
    Pump 2500
}

Write-Log "Ready"
if (-not $Prepare) {
    Open-InBrowser
    Pump 1500
    $Splash.Close()
}
exit 0
