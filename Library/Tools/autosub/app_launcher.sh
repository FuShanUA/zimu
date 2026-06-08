#!/bin/bash
# AutoSub Launcher App Wrapper (Mac Terminal Version)
# Correct Tool Directory
TOOLDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Launch a new Terminal window and run the Batch Pro directly
osascript -e "tell application \"Terminal\"
    activate
    do script \"cd '$TOOLDIR' && source .venv/bin/activate && python3 autosub_batch_pro.py\"
end tell"
