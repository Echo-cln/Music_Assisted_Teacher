@echo off
setlocal
cd /d "%~dp0"

echo [setup] Creating an isolated CPU environment for music stem separation...
if not exist ".audio-separator-venv\Scripts\python.exe" (
  py -3.11 -m venv .audio-separator-venv
  if errorlevel 1 (
    echo [error] Python 3.11 launcher was not found. Install Python 3.11 or create .audio-separator-venv manually.
    exit /b 1
  )
)

.audio-separator-venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 exit /b 1

.audio-separator-venv\Scripts\python.exe -m pip install "audio-separator[cpu]"
if errorlevel 1 (
  echo [error] Audio Separator installation failed. The main application environment was not modified.
  exit /b 1
)

.audio-separator-venv\Scripts\audio-separator.exe --env_info
if errorlevel 1 exit /b 1

echo.
echo [done] The optional separator is ready. The BS-RoFormer model weights download on first use.
echo [note] CPU separation can take several minutes. To use an NVIDIA GPU, follow the official audio-separator GPU install guide.
pause
