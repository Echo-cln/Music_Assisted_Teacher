@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [error] Please run run.bat once first so the project .venv is created.
  pause
  exit /b 1
)

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
echo [setup] Installing the Demucs vocal-separation component into this project's .venv...
"%PYTHON_EXE%" -m pip install -r backend\requirements-audio-pro.txt
if errorlevel 1 goto :error

echo [ok] Demucs is installed. The first mixed-reference analysis will download its model weights.
echo [next] Start the application with run.bat, then test 20-40 seconds of one reference singer and one matching practice recording.
pause
exit /b 0

:error
echo [error] Installation failed. Please copy the output above and send it to me.
pause
exit /b 1
