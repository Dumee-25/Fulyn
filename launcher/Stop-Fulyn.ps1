<#
  Stops Fulyn's containers to free memory. Your data stays in the database volume.
  Docker Desktop and Ollama are left running.
#>

$Root = Split-Path -Parent $PSScriptRoot
Add-Type -AssemblyName System.Windows.Forms

Push-Location $Root
try {
    & docker compose -f docker-compose.yml -f docker-compose.prod.yml stop *> $null
    $ok = $LASTEXITCODE -eq 0
} finally {
    Pop-Location
}

if ($ok) {
    [System.Windows.Forms.MessageBox]::Show("Fulyn has stopped.", "Fulyn", "OK", "Information") | Out-Null
} else {
    [System.Windows.Forms.MessageBox]::Show(
        "Could not stop Fulyn. Is Docker running?", "Fulyn", "OK", "Warning"
    ) | Out-Null
}
