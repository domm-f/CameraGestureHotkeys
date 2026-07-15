@echo off
setlocal
cd /d "%~dp0"
title CameraGestureHotkeys

if not exist ".venv\Scripts\python.exe" (
    echo The app has not been set up yet.
    echo Run SETUP.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" app.py
if errorlevel 1 (
    echo.
    echo The app closed because of an error.
    pause
)
