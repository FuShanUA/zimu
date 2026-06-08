---
name: autosub
description: End-to-End automated subtitling workflow (Download -> Transcribe -> Translate -> Hardsub).
---

# AutoSub Skill

A fully automated "zero-click" workflow to generate professional bilingual subtitles for videos.

## Workflow
1.  **Download**: Fetches video from URL (YouTube/X/Bilibili) using `vdown`.
2.  **Transcribe**: Generates English SRT using `transcriber` (Whisper Large V2).
3.  **Translate**: Translates to Chinese using AI (Gemini, ChatGPT, Kimi, Qwen, or GLM) with "Humanizer" style rules.
4.  **Burn**: Generates `hardsub` video with professional vector-box styling (`hardsubber`).

## Usage

### GUI Mode (Recommended)
```powershell
python /Users/shanfu/cc/Library/Tools/autosub/autosub_gui.py
```

### Command Line Mode
```powershell
python /Users/shanfu/cc/Library/Tools/autosub/autosub.py <URL|FILE> [options]
```

### Advanced Translation Strategy (IDE Mode)
When using the `ide` translator (default), the Agent MUST follow this strategy:
1.  **Smart Chunking**: Do NOT translate line-by-line blindly. Read 3 lines at a time (Context Window) to solve sentence fragmentation.
2.  **Verbalize First**: Apply `verbalizer` principles (Tone/Persona) during the initial translation draft.
3.  **Humanize First**: Apply `humanizer-zh` rules (De-AI) to polish the drafted text.
4.  **No Reverse Explanations**: Do NOT include the original English term in parentheses after translation (e.g., avoid `韧性（Persistent）`).
5.  **Sync Check**: Verify strict block count matching before saving.

### Options
*   `--model`: Whisper model (default: `large-v2`).
*   `--translator`: `api` (Gemini Flash) or `ide` (Agent Assisted). Default: `ide`.
*   `--style`: Translation tone (`casual`, `formal`, `edgy`). Default: `casual`.
*   `--layout`: Subtitle layout (`bilingual`, `cn`, `en`). Default: `bilingual`.
*   `--cookies`: Path to cookies.txt for restricted videos.

## Examples

**URL Download & Process**:
```bash
python autosub.py "https://youtube.com/watch?v=..."
```

**Local File Process**:
```bash
python autosub.py "d:\videos\presentation.mp4" --style formal
```

**Monolingual Output**:
```bash
python autosub.py "https://x.com/..." --layout cn
```

## Configuration

The default values for all parameters are managed via external JSON files:
1.  **Defaults (`defaults.json`)**: Factory settings included in the distribution.
2.  **Overrides (`settings.json`)**: Optional user-created file in the same directory as the executable/script to customize defaults without code changes.

## Requirements
*   `GEMINI_API_KEY` or `GOOGLE_API_KEY` in environment (or `.env`).
*   `vdown`, `transcriber`, `hardsubber` skills installed.