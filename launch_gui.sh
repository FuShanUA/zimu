#!/bin/bash
export PYTHONPATH="Library/Tools/common:Library/Tools/autosub:Library/Tools/transcriber:Library/Tools/vdown:Library/Tools/hardsubber"

VENV_PYTHON="Library/Tools/autosub/.venv/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ Error: Virtual environment not found. Please run setup_env.sh first."
    exit 1
fi

echo "🚀 Launching AutoSub GUI..."
"$VENV_PYTHON" Library/Tools/autosub/autosub_gui.py "$@"
