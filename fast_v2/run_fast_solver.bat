@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set OMP_NUM_THREADS=2
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
set "SOLVER_PYTHONW=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
if not exist "%SOLVER_PYTHONW%" exit /b 1
start "" "%SOLVER_PYTHONW%" "%~dp0tray_app.py" %*
endlocal
