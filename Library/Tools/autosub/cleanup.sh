#!/bin/bash

# 🛠️ AutoSub Folder Cleanup Script
# Organizes 76 loose files into clean, dedicated subdirectories.

CURRENT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$CURRENT_DIR"

echo "🧹 Starting AutoSub directory cleanup..."

# 1. Create subdirectories if they don't exist
mkdir -p tests artwork legacy logs

# ==============================================================================
# 2. Move Test Files to tests/
# ==============================================================================
echo "📦 Organizing unit tests..."
TEST_FILES=(
    "test_autosub_gui.py"
    "test_autosub_state.py"
    "test_connection_cli.py"
    "test_env_debug.py"
    "test_gdrive_basic.py"
    "test_gdrive_list.py"
    "test_gemini_api.py"
    "test_list_models.py"
    "test_vertex_global.py"
)

for file in "${TEST_FILES[@]}"; do
    if [ -f "$file" ]; then
        mv "$file" tests/
    fi
done

# ==============================================================================
# 3. Move Alternative Artwork / Drafts to artwork/
# ==============================================================================
# Note: We KEEP "autosub_vibrant_v2.png" and "autosub.ico" in the root since
# autosub_gui.py explicitly references them at CURRENT_DIR root.
echo "🎨 Organizing design drafts and alternative icons..."
ART_FILES=(
    "autosub.png"
    "autosub_apple_v2.ico"
    "autosub_apple_v2.png"
    "autosub_batch_v4.ico"
    "autosub_ios_v1.ico"
    "autosub_ios_v1.png"
    "autosub_launcher.png"
    "autosub_launcher_real.png"
    "autosub_launcher_v2.png"
    "autosub_launcher_v2_real.png"
    "autosub_launcher_v3.png"
    "autosub_launcher_v3_real.png"
    "autosub_pipeline_v5.ico"
    "autosub_premium_v6.png"
    "autosub_pro_v3.ico"
    "autosub_tiffany_v6.ico"
    "autosub_v9.ico"
    "autosub_vibrant.png"
    "autosub_vibrant_v2.ico"
    "autosub_vibrant_v2_restored.png"
    "launcher.icns"
    "launcher_v2.icns"
    "launcher_v3.icns"
)

for file in "${ART_FILES[@]}"; do
    if [ -f "$file" ]; then
        mv "$file" artwork/
    fi
done

# ==============================================================================
# 4. Move Legacy Scripts, Bat files, and Scratchpads to legacy/
# ==============================================================================
echo "💾 Archiving older versions and Windows bat files..."
LEGACY_FILES=(
    "autosub_batch.py.bak"
    "autosub_batch_v3.py"
    "autosub_batch_v4.py"
    "launch_AIPCon_3.bat"
    "launch_autosub_v4.bat"
    "launch_batch_pro.bat"
    "launch_devcon_4.bat"
    "reproduce_bug.py"
    "debug_discover.py"
    "convert_icon.py"
    "convert_to_icns.sh"
    "watch.sh"
    "autosub_launcher.py_imports.tmp"
    "ffmpeg.zip"
)

for file in "${LEGACY_FILES[@]}"; do
    if [ -f "$file" ]; then
        mv "$file" legacy/
    fi
done

# ==============================================================================
# 5. Move log files to logs/
# ==============================================================================
echo "📝 Moving logs..."
LOG_FILES=(
    "autosub_batch.log"
    "crash.log"
    "launcher_debug.log"
    "gui_crash_report.txt"
)

for file in "${LOG_FILES[@]}"; do
    if [ -f "$file" ]; then
        mv "$file" logs/
    fi
done

echo "✨ AutoSub directory cleanup complete! Folders organized: tests/, artwork/, legacy/, logs/."
