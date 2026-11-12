@echo off
REM ===== Checks Python, packages, .env, use case and the API key (makes one tiny AI call). =====
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
if not exist .venv (echo Run 1_setup.bat first & pause & exit /b 1)
call .venv\Scripts\activate.bat
python scripts\check_setup.py
pause
