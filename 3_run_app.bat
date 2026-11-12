@echo off
REM ===== Starts the app. Browser opens at http://localhost:8501  (close this window to stop). =====
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
if not exist .venv (echo Run 1_setup.bat first & pause & exit /b 1)
call .venv\Scripts\activate.bat
python scripts\seed_samples.py
streamlit run app.py
pause
