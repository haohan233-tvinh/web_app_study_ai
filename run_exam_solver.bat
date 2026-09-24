@echo off
setlocal
chcp 65001 >nul
title Web MCQ - Offline
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set OMP_NUM_THREADS=2
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
set "SOLVER_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%SOLVER_PYTHON%" set "SOLVER_PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%SOLVER_PYTHON%" (
  echo Khong tim thay Python. Xem README.md de cai dat.
  pause
  exit /b 1
)
"%SOLVER_PYTHON%" "%~dp0clipboard_solver.py" %*
if errorlevel 1 pause
endlocal
