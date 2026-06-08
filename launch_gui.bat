@echo off
set PYTHONPATH=Library\Tools\common;Library\Tools\autosub;Library\Tools\transcriber;Library\Tools\vdown;Library\Tools\hardsubber

set VENV_PYTHON=Library\Tools\autosub\.venv\Scripts\python.exe

if not exist "%VENV_PYTHON%" (
    echo ❌ Error: Virtual environment not found. Please run setup_env.bat first.
    pause
    exit /b 1
)

echo 🚀 Launching AutoSub GUI...
"%VENV_PYTHON%" Library\Tools\autosub\autosub_gui.py %*
