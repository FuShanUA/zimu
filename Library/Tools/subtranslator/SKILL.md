---
name: subtranslator
description: Wrapper skill to manage the subtranslator tool for translating subtitles.
---

# Subtranslator Skill

This skill provides a command-line interface via `subtranslator.py` to manage the lifecycle of subtitle translation (splitting, merging, and validation).

## User Guide
The linguistic rules, anti-translationese guidelines, and formatting constraints are documented in [README.md](./README.md). **Always refer to README.md before performing any translation tasks to ensure native-level quality.**

## Technical Workflow

1.  **Split**:
    -   Divide a large SRT file into chunks for processing.
    -   Command: `python /Users/shanfu/cc/Library/Tools/subtranslator/subtranslator.py split <input.srt>`
    -   Targets: Creates `chunks/*.srt`.

2.  **Translation**:
    -   Translate the generated chunks.
    -   Follow the rules in `README.md` (e.g., de-personalizing "you", handling fillers).

3.  **Merge**:
    -   Combine the translated chunks with the original English to create a bilingual SRT.
    -   Command: `python /Users/shanfu/cc/Library/Tools/subtranslator/subtranslator.py merge <input.srt>`
    -   Output: Generates `<filename>.bilingual.srt`.

4.  **Validate**:
    -   Verify the final output for structural integrity.
    -   Command: `python /Users/shanfu/cc/Library/Tools/subtranslator/subtranslator.py validate <output.srt>`

## Portability Note
All commands should be run using absolute paths or from the skill directory. If running from the project root, use `python /Users/shanfu/cc/Library/Tools/subtranslator/subtranslator.py`.

## When to Use
1.  Preparing raw English subtitles for translation.
2.  Merging translated blocks back into a final bilingual format.
3.  Ensuring translated content follows our "Anti-Translationese" standards.