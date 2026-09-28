@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [setup] Creating Python 3.11 virtual environment...
  py -3.11 -m venv .venv || goto :error
)

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
"%PYTHON_EXE%" -c "import fastapi, librosa, json_repair" >nul 2>&1
if errorlevel 1 (
  echo [setup] Installing project dependencies into .venv only...
  "%PYTHON_EXE%" -m pip install --upgrade pip || goto :error
  "%PYTHON_EXE%" -m pip install -r backend\requirements.txt || goto :error
)

if not exist "backend\.env" (
  echo [warning] backend\.env is missing. Copy backend\.env.example to backend\.env and fill in the AI settings before generating lessons.
)

echo [start] Open http://127.0.0.1:8000 after the server is ready.
start "" http://127.0.0.1:8000
cd backend
"%PYTHON_EXE%" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
goto :eof

:error
echo.
echo [error] Startup failed. Please copy the output above and send it to me.
pause
exit /b 1
