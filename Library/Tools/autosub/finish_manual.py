
import os
import sys
import re

# Add paths to tools
TOOLS_DIR = r"/Users/shanfu/cc/Library/Tools"
srt_path = r"/Users/shanfu/cc/results/We_re_All_Addicted_To/We're All Addicted To Claude Code [qwmmWzPnhog].srt"
video_path = r"/Users/shanfu/cc/download/We're All Addicted To Claude Code [qwmmWzPnhog].mp4"

# Load LLM Utils
sys.path.append(os.path.join(TOOLS_DIR, "common"))
import llm_utils
llm_client = llm_utils.get_client()

def translate_content(content):
    prompt = f"""
Translate the following English subtitles (SRT format) into Simplified Chinese.
Output ONLY the translated SRT content. Do not include markdown code blocks.

Style Guide (casual):
- Use natural, spoken Chinese (口语化).
- NO "translationese".
- Keep all timecodes exactly as is.

Subtitle Content:
{content}
"""
    # Use the unified client which handles Vertex vs Gemini routing
    return llm_client.generate_content(prompt, model_name="gemini-3.1-pro")

print("🌍 Translating SRT...")
with open(srt_path, "r", encoding="utf-8") as f:
    full_content = f.read()

# For very large files, we might need to chunk. 100k characters is usually fine for one shot if it's SRT.
# Total lines: 4749, Total bytes: 98,762. This should fit in one or two goes.
# Let's chunk every 1000 lines just to be safe and avoid hitting output limits.
lines = full_content.splitlines()
chunk_size = 1000
chunks = [lines[i:i + chunk_size] for i in range(0, len(lines), chunk_size)]

translated_chunks = []
for i, chunk in enumerate(chunks):
    print(f"  Chunk {i+1}/{len(chunks)}...")
    chunk_text = "\n".join(chunk)
    translated = translate_content(chunk_text)
    # Cleanup markdown
    translated = re.sub(r"^```\w*\n", "", translated)
    translated = re.sub(r"\n```$", "", translated)
    translated_chunks.append(translated)

zh_srt_path = srt_path.replace(".srt", ".zh.srt")
with open(zh_srt_path, "w", encoding="utf-8") as f:
    f.write("\n".join(translated_chunks))

print(f"✅ Translated SRT saved: {zh_srt_path}")

# Merge and Burn
sys.path.append(os.path.join(TOOLS_DIR, "subtranslator", "lib"))
import srt_utils

bi_srt_path = srt_path.replace(".srt", ".bi.srt")
print("🔀 Merging tracks...")
srt_utils.merge_tracks(zh_srt_path, srt_path, bi_srt_path)

# Burn
SRT2ASS_CMD = [sys.executable, os.path.join(TOOLS_DIR, "hardsubber", "srt_to_ass.py")]
BURNSUB_CMD = [sys.executable, os.path.join(TOOLS_DIR, "hardsubber", "burn_engine.py")]

ass_path = bi_srt_path.replace(".srt", ".ass")
print("🎬 Generating ASS...")
import subprocess
subprocess.run(list(SRT2ASS_CMD) + [bi_srt_path, ass_path, "--layout", "bilingual", "--main-lang", "cn", "--cn-font", "KaiTi"], check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == "win32" else 0)

out_video = video_path.replace(".mp4", "_hardsub.mp4")
print("🔥 Burning...")
subprocess.run(list(BURNSUB_CMD) + [video_path, ass_path, out_video], check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == "win32" else 0)

print(f"✨ ALL DONE! Video saved at: {out_video}")