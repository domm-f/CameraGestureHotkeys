@echo off
setlocal
cd /d "%~dp0"
title Camera Gesture Hotkeys - Build Installer

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_setup.ps1"
if errorlevel 1 (
    echo.
    echo The setup file was not built.
    pause
    exit /b 1
)

echo.
echo The finished installer is in the release folder.
pause
