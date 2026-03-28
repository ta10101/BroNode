# Run BroNode from source: venv, deps, then GUI. Requires Python 3.10+ with Tkinter.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$usePyLauncher = $false
if (Get-Command py -ErrorAction SilentlyContinue) {
    $usePyLauncher = $true
} elseif (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "No Python found. Install Python 3.10+ (with tcl/tk on Windows) and add it to PATH."
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating .venv ..."
    if ($usePyLauncher) {
        py -3 -m venv .venv
    } else {
        python -m venv .venv
    }
}

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Error "venv missing at .venv\Scripts\python.exe"
}

Write-Host "Installing dependencies ..."
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r requirements.txt

Write-Host "Starting BroNode (close the window to exit) ..."
& $venvPy app.py
