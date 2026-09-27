<#
  Creates "Fulyn" and "Stop Fulyn" shortcuts in the Start menu and on the desktop.
  Run once (again after moving the project folder):
    powershell -ExecutionPolicy Bypass -File launcher\Install-Shortcuts.ps1
  Remove with: -Uninstall
#>

param([switch]$Uninstall)

$Launcher = $PSScriptRoot
$Icon = Join-Path $Launcher "fulyn.ico"
$StartMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "Fulyn"
$Desktop = [Environment]::GetFolderPath("Desktop")

$shortcuts = @(
    @{ Name = "Fulyn"; Dirs = @($StartMenu, $Desktop); Description = "Open Fulyn" },
    @{ Name = "Stop Fulyn"; Dirs = @($StartMenu); Description = "Stop Fulyn to free memory" }
)

if ($Uninstall) {
    foreach ($s in $shortcuts) {
        foreach ($dir in $s.Dirs) { Remove-Item (Join-Path $dir "$($s.Name).lnk") -ErrorAction SilentlyContinue }
    }
    Remove-Item $StartMenu -ErrorAction SilentlyContinue
    Write-Output "Shortcuts removed."
    return
}

New-Item -ItemType Directory -Force -Path $StartMenu | Out-Null

# Fulyn opens in Fulyn.exe, which has its own window and taskbar identity (so pinning it
# pins Fulyn, not the browser). Build it if needed.
$App = Join-Path $Launcher "bin\Fulyn.exe"
if (-not (Test-Path $App)) {
    & (Join-Path $Launcher "Build-App.ps1")
}

# Stop Fulyn: PowerShell without a console window (conhost --headless, Windows 11).
$conhost = Join-Path $env:SystemRoot "System32\conhost.exe"
$powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$stopArgs = "--headless `"$powershell`" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$(Join-Path $Launcher 'Stop-Fulyn.ps1')`""

$shell = New-Object -ComObject WScript.Shell
foreach ($s in $shortcuts) {
    foreach ($dir in $s.Dirs) {
        $link = $shell.CreateShortcut((Join-Path $dir "$($s.Name).lnk"))
        if ($s.Name -eq "Fulyn") {
            $link.TargetPath = $App
            $link.Arguments = ""
            $link.IconLocation = "$App,0"
        } else {
            $link.TargetPath = $conhost
            $link.Arguments = $stopArgs
            $link.IconLocation = "$Icon,0"
        }
        $link.WorkingDirectory = $Launcher
        $link.Description = $s.Description
        $link.Save()
    }
}

Write-Output "Shortcuts created in the Start menu (Fulyn folder) and on the desktop."
Write-Output "To pin: right-click Fulyn in Start (or its taskbar button while open) and choose Pin to taskbar."
