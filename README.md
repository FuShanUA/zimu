# AutoSub Suite

A self-contained, offline-first automated video transcription, translation, and hardsubtitle-burning suite. Supports Apple Silicon GPU acceleration (via MLX) and batch processing.

## Project Structure

```
autosub-app/
├── Library/
│   └── Tools/
│       ├── common/          # Shared utilities (LLMs, SRT utils)
│       ├── autosub/         # Main execution, GUI, batch logic, and launcher
│       ├── vdown/           # Video download handlers
│       ├── transcriber/     # Local FastWhisper/MLX transcription
│       ├── subtranslator/   # Subtitle translation and alignment
│       └── hardsubber/      # Subtitle styling (ASS) and FFmpeg burn engines
├── setup_env.sh             # Setup environment (macOS/Linux)
├── setup_env.bat            # Setup environment (Windows)
├── launch_gui.sh / .bat     # Launch Graphical Interface
├── launch_launcher.sh / .bat # Launch Interactive Task Launcher
└── README.md
```

## Prerequisites

1. **Python 3.10 - 3.12** is required.
2. **FFmpeg** must be installed and added to your system `PATH`.
   - **macOS**: `brew install ffmpeg`
   - **Windows**: Download Gyan's build of FFmpeg and add the `bin` folder to your Path.
3. **Node.js** (Optional, recommended for YouTube downloads to resolve JS player challenges).
   - **macOS**: `brew install node`

---

## Quick Start Setup

### Step 1: Initialize Virtual Environment & Install Dependencies

Run the setup script for your platform:

- **macOS / Linux**:
  ```bash
  ./setup_env.sh
  ```
- **Windows**:
  Double-click `setup_env.bat` or run in CMD:
  ```cmd
  setup_env.bat
  ```

*This script will create a virtual environment in `Library/Tools/autosub/.venv`, upgrade pip, install all dependencies, and dynamically install Apple Silicon GPU acceleration packages (on Apple Silicon macOS).*

### Step 2: Configure API Keys

1. Rename the generated `.env` file (copied from `.env.example`).
2. Open `.env` and fill in your LLM API Keys (e.g. `GEMINI_API_KEY`).

---

## Running the Application

### 1. Graphical User Interface (GUI)
Run:
- **macOS / Linux**: `./launch_gui.sh`
- **Windows**: Run `launch_gui.bat`

### 2. Interactive CLI Task Launcher (Batch Pro)
Run:
- **macOS / Linux**: `./launch_launcher.sh`
- **Windows**: Run `launch_launcher.bat`

---

## Developer / Troubleshooting Tips
- **Logs**: Detailed execution logs for each video process are stored under `workflow.log` inside the output project directory.
- **Lock Files**: If an active project hangs, check for `batch_engine.lock` inside the project folder.
