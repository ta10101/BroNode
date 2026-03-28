@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating .venv ...
  where py >nul 2>&1 && py -3 -m venv .venv || python -m venv .venv
)

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Could not create venv. Install Python 3.10+ from python.org
  pause
  exit /b 1
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip -q
python -m pip install -r requirements.txt -q
echo Starting BroNode ...
python app.py
pause
