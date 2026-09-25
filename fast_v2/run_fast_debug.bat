@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set OMP_NUM_THREADS=2
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" tray_app.py %*
if errorlevel 1 pause
endlocal
