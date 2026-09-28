@echo off
setlocal
cd /d "%~dp0"

rem A virtual environment stores the absolute path of the Python that created it.
rem If that Python was removed (for example D:\python\python.exe), recreate only
rem this project's .venv instead of accidentally using Anaconda's global packages.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys" >nul 2>&1
  if errorlevel 1 (
    echo [repair] Existing .venv points to a missing Python and will be rebuilt...
    rmdir /s /q ".venv"
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo [setup] Creating Python 3.11 virtual environment...
  py -3.11 -m venv .venv || goto :error
)

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
"%PYTHON_EXE%" -c "import fastapi, librosa, json_repair, imageio_ffmpeg" >nul 2>&1
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
