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
    @{ Name = "Fulyn"; Script = "Fulyn.ps1"; Dirs = @($StartMenu, $Desktop); Description = "Open Fulyn" },
    @{ Name = "Stop Fulyn"; Script = "Stop-Fulyn.ps1"; Dirs = @($StartMenu); Description = "Stop Fulyn to free memory" }
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

# conhost --headless runs PowerShell without flashing a console window (Windows 11).
$conhost = Join-Path $env:SystemRoot "System32\conhost.exe"
$powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

$shell = New-Object -ComObject WScript.Shell
foreach ($s in $shortcuts) {
    $script = Join-Path $Launcher $s.Script
    $arguments = "--headless `"$powershell`" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
    foreach ($dir in $s.Dirs) {
        $link = $shell.CreateShortcut((Join-Path $dir "$($s.Name).lnk"))
        $link.TargetPath = $conhost
        $link.Arguments = $arguments
        $link.WorkingDirectory = $Launcher
        $link.IconLocation = "$Icon,0"
        $link.Description = $s.Description
        $link.WindowStyle = 7  # minimized
        $link.Save()
    }
}

Write-Output "Shortcuts created in the Start menu (Fulyn folder) and on the desktop."
Write-Output "To pin: open Start, find Fulyn, right-click, Pin to taskbar."
