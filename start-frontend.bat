@echo off
REM Market-Spine Trading Desktop Launcher (Windows Batch)
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0start-frontend.ps1"
pause
