# Requires WiX Toolset 3.11+ on PATH (candle.exe, light.exe)
# https://wixtoolset.org/docs/wix3/

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$DistExe = Join-Path $Root "dist\BroNode.exe"

if (-not (Test-Path $DistExe)) {
    Write-Error "Missing $DistExe — build the exe first: cd '$Root'; python -m PyInstaller --noconfirm BroNode.spec"
}

$WixBin = @(
    "${env:ProgramFiles(x86)}\WiX Toolset v3.14\bin",
    "${env:ProgramFiles(x86)}\WiX Toolset v3.11\bin",
    "${env:ProgramFiles}\WiX Toolset v3.14\bin"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($WixBin) {
    $env:Path = "$WixBin;$env:Path"
}

$candle = Get-Command candle -ErrorAction SilentlyContinue
$light = Get-Command light -ErrorAction SilentlyContinue
if (-not $candle -or -not $light) {
    Write-Error "WiX candle/light not found. Install WiX Toolset v3 and add bin to PATH."
}

$OutDir = Join-Path $PSScriptRoot "build"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$abs = (Resolve-Path $DistExe).Path
& candle.exe -dBroNodeExe="$abs" -out "$OutDir\" (Join-Path $PSScriptRoot "BroNode.wxs")
# WixUI_InstallDir in BroNode.wxs (wizard with progress) requires WixUIExtension.
& light.exe -ext WixUIExtension -out (Join-Path $Root "dist\BroNodeSetup.msi") (Join-Path $OutDir "BroNode.wixobj")

Write-Host "MSI: $(Join-Path $Root 'dist\BroNodeSetup.msi')"
