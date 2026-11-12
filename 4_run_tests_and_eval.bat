@echo off
REM ===== Runs automated tests + accuracy evaluation (evidence for D4). =====
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
call .venv\Scripts\activate.bat
pytest -q
python -m eval.run_eval
echo.
echo Report saved in usecases\YOUR_USECASE\eval_report_PROVIDER.md
pause
