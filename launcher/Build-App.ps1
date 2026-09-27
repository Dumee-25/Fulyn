<#
  Builds launcher\bin\Fulyn.exe, a small Windows app that hosts Fulyn in its own window
  (so it has its own taskbar icon and can be pinned).

  Uses the C# compiler that ships with Windows (.NET Framework 4.x); no SDK needed.
  Downloads Microsoft's WebView2 SDK package from nuget.org once (pinned version).
  The Edge WebView2 runtime must be installed (it is on Windows 11).
#>

$ErrorActionPreference = "Stop"
$WebView2Version = "1.0.4191.47"

$Launcher = $PSScriptRoot
$Deps = Join-Path $Launcher ".deps"
$Bin = Join-Path $Launcher "bin"
$Csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"

if (-not (Test-Path $Csc)) { throw "C# compiler not found at $Csc" }
New-Item -ItemType Directory -Force -Path $Deps, $Bin | Out-Null

$package = Join-Path $Deps "webview2-$WebView2Version"
if (-not (Test-Path $package)) {
    $zip = "$package.zip"
    $url = "https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/$WebView2Version/microsoft.web.webview2.$WebView2Version.nupkg"
    Write-Output "Downloading WebView2 SDK $WebView2Version..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $package -Force
    Remove-Item $zip
}

$core = Join-Path $package "lib\net462\Microsoft.Web.WebView2.Core.dll"
$winforms = Join-Path $package "lib\net462\Microsoft.Web.WebView2.WinForms.dll"
$loader = Join-Path $package "runtimes\win-x64\native\WebView2Loader.dll"
foreach ($file in @($core, $winforms, $loader)) {
    if (-not (Test-Path $file)) { throw "Missing $file in the WebView2 package" }
    Copy-Item $file $Bin -Force
}

& $Csc /nologo /target:winexe /platform:x64 /optimize+ `
    "/out:$(Join-Path $Bin 'Fulyn.exe')" `
    "/win32icon:$(Join-Path $Launcher 'fulyn.ico')" `
    "/r:$(Join-Path $Bin 'Microsoft.Web.WebView2.Core.dll')" `
    "/r:$(Join-Path $Bin 'Microsoft.Web.WebView2.WinForms.dll')" `
    /r:System.Windows.Forms.dll /r:System.Drawing.dll `
    (Join-Path $Launcher "app\Fulyn.cs")
if ($LASTEXITCODE -ne 0) { throw "Compilation failed" }

Write-Output "Built $(Join-Path $Bin 'Fulyn.exe')"
