# Build BroNode for Windows: PyInstaller one-file exe; optional MSI (WiX).
param(
    [switch]$Msi
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Installing build deps..."
python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt

Write-Host "PyInstaller (BroNode.spec)..."
python -m PyInstaller --noconfirm BroNode.spec

Write-Host ""
Write-Host "Done: .\dist\BroNode.exe"

if ($Msi) {
    Write-Host "Building MSI (WiX)..."
    & "$PSScriptRoot\packaging\wix\build_msi.ps1"
} else {
    Write-Host "Optional MSI: .\build.ps1 -Msi   (requires WiX Toolset v3, candle/light on PATH)"
}
