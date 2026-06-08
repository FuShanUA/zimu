@echo off
setlocal enabledelayedexpansion

set VENV_DIR=Library\Tools\autosub\.venv

echo === AutoSub Environment Setup (Windows) ===

:: Check for Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo ❌ Error: python is not installed or not in PATH.
    pause
    exit /b 1
)

:: Create virtual environment if it doesn't exist
if not exist "%VENV_DIR%" (
    echo 📂 Creating virtual environment in %VENV_DIR%...
    python -m venv "%VENV_DIR%"
) else (
    echo ✔ Virtual environment already exists.
)

set VENV_PYTHON=%VENV_DIR%\Scripts\python.exe

echo ⚙ Upgrading pip...
"%VENV_PYTHON%" -m pip install --upgrade pip

echo 📦 Installing requirements from requirements.txt...
"%VENV_PYTHON%" -m pip install -r requirements.txt

:: Create default .env if it doesn't exist
if not exist ".env" (
    echo 📄 Copying .env.example to .env...
    copy .env.example .env
    echo 💡 Please edit .env and insert your API keys.
) else (
    echo ✔ Existing .env file found. Skipping copy.
)

echo === Setup Completed Successfully! ===
echo You can now run launch_gui.bat or launch_launcher.bat
pause
