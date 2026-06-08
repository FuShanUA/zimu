#!/bin/bash
set -e

# Target directory for virtual environment
VENV_DIR="Library/Tools/autosub/.venv"

echo "=== AutoSub Environment Setup ==="

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is not installed or not in PATH."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✔ Found Python $PYTHON_VERSION"

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "📂 Creating virtual environment in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
else
    echo "✔ Virtual environment already exists."
fi

# Determine virtual environment executable path
VENV_PIP="$VENV_DIR/bin/pip"
VENV_PYTHON="$VENV_DIR/bin/python"

echo "⚙ Upgrading pip..."
"$VENV_PYTHON" -m pip install --upgrade pip

echo "📦 Installing requirements from requirements.txt..."
"$VENV_PYTHON" -m pip install -r requirements.txt

# Conditional MLX GPU acceleration for Apple Silicon macOS
OS_TYPE=$(uname -s)
ARCH_TYPE=$(uname -m)

if [ "$OS_TYPE" = "Darwin" ] && [ "$ARCH_TYPE" = "arm64" ]; then
    echo "🍏 Apple Silicon macOS detected. Installing MLX GPU-accelerated libraries..."
    "$VENV_PYTHON" -m pip install mlx mlx-metal mlx-whisper
else
    echo "ℹ Non-Apple Silicon or non-macOS platform. Skipping MLX GPU libraries."
fi

# Create default .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "📄 Copying .env.example to .env..."
    cp .env.example .env
    echo "💡 Please edit .env and insert your API keys."
else
    echo "✔ Existing .env file found. Skipping copy."
fi

echo "=== Setup Completed Successfully! ==="
echo "You can now run launch_gui.sh or launch_launcher.sh"
