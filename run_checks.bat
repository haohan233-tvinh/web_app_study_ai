@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set "SOLVER_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%SOLVER_PYTHON%" set "SOLVER_PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
"%SOLVER_PYTHON%" doctor.py
if errorlevel 1 goto done
"%SOLVER_PYTHON%" -m unittest discover -s tests -p "test_*.py" -v
:done
pause
endlocal
