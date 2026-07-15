@echo off
setlocal
cd /d "%~dp0"
title CameraGestureHotkeys - Setup

echo ========================================
echo Camera Gesture Hotkeys - First-time setup
echo ========================================
echo.

py -3.11 --version >nul 2>&1
if %errorlevel%==0 (
    set "PY=py -3.11"
) else (
    py -3 --version >nul 2>&1
    if not %errorlevel%==0 (
        echo Python was not found.
        echo Install 64-bit Python 3.11, enable "Add Python to PATH", then run SETUP.bat again.
        pause
        exit /b 1
    )
    set "PY=py -3"
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the private Python environment...
    %PY% -m venv .venv
    if errorlevel 1 goto :failed
)

echo Installing required packages...
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 goto :failed
python -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo Downloading the pose-recognition model...
python download_model.py
if errorlevel 1 goto :failed

echo.
echo Setup completed successfully.
echo Double-click RUN_APP.bat to start the app.
pause
exit /b 0

:failed
echo.
echo Setup failed. Read the error above.
pause
exit /b 1
