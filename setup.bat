@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv" py -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
cd backend
if not exist ".env" copy .env.example .env >nul
python scripts\import_excel.py
python scripts\seed_demo.py
echo.
echo Setup complete. Run run.bat next.
pause

