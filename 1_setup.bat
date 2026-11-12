@echo off
REM ===== One-time setup (double-click). Creates a private Python environment and installs everything. =====
cd /d "%~dp0"
echo.
echo [1/4] Checking Python...
where python >nul 2>nul
if errorlevel 1 (
  echo Python is NOT installed or not on PATH.
  echo Install Python 3.12 from https://www.python.org/downloads/  and TICK "Add python.exe to PATH".
  pause
  exit /b 1
)
python --version
echo.
echo [2/4] Creating virtual environment (.venv)...
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
echo.
echo [3/4] Installing packages (2-5 minutes)...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Package install FAILED. On office network try: mobile hotspot, or
  echo   pip install -r requirements.txt --proxy http://YOUR_PROXY:PORT
  pause
  exit /b 1
)
echo.
echo [4/4] Creating .env settings file...
if not exist .env (
  copy .env.example .env >nul
  echo .env created. Open it in VS Code / Notepad to add your API key.
) else (
  echo .env already exists - not changed.
)
echo.
echo SETUP DONE. Next: edit .env, then double-click 2_check_setup.bat
pause
