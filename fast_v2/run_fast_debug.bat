@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set OMP_NUM_THREADS=2
set "SOLVER_PYTHON=%~dp0..\.venv\Scripts\python.exe"
if not exist "%SOLVER_PYTHON%" set "SOLVER_PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
"%SOLVER_PYTHON%" tray_app.py %*
if errorlevel 1 pause
endlocal
