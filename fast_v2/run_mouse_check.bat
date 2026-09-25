@echo off
setlocal
cd /d "%~dp0"
set "CHECK_PYTHON=%~dp0..\.venv\Scripts\pythonw.exe"
if not exist "%CHECK_PYTHON%" set "CHECK_PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
if not exist "%CHECK_PYTHON%" exit /b 1
start "" "%CHECK_PYTHON%" "%~dp0check_mouse_buttons.py"
endlocal
