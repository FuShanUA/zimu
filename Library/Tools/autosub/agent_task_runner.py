
import os
import sys
import argparse
import time
import re
import json

# Ensure lib exists
if getattr(sys, 'frozen', False):
    BUNDLE_DIR = sys._MEIPASS
    TOOLS_DIR = os.path.join(BUNDLE_DIR, "Library", "Tools")
else:
    TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.append(os.path.join(TOOLS_DIR, "subtranslator", "lib"))
sys.path.append(os.path.join(TOOLS_DIR, "common"))

try:
    import srt_utils
except ImportError:
    # Fallback local
    sys.path.append(os.path.join(TOOLS_DIR, "subtranslator", "lib"))
    try:
        import srt_utils
    except ImportError:
        print("Error: srt_utils not found.")
        sys.exit(1)

# --- SKILL INTEGRATION ---
def load_skill_rules(tool_name):
    skill_dir = os.path.join(TOOLS_DIR, tool_name)
    readme_path = os.path.join(skill_dir, "README.md")
    content = ""
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            content = f.read()
    return content

HUMANIZER_RULES = load_skill_rules("humanizer-zh")
VERBALIZER_RULES = load_skill_rules("verbalizer")

def process_chunk_with_agent(chunk_path, style="casual"):
    """
    Simulates the Agent processing a chunk file by reading it,
    printing instructions for the Agent (User), and waiting for the file to be updated.

    In a true automated IDE loop, the Agent (Me) would intercept this output and perform the action.
    """
    print(f"\n--- [AGENT TASK] Translate Chunk: {os.path.basename(chunk_path)} ---")

    # Read the chunk content to display (simulating "View")
    with open(chunk_path, 'r', encoding='utf-8') as f:
        content = f.read()

    print(f"INPUT CONTENT ({len(content)} bytes):")
    print(content[:500] + "..." if len(content) > 500 else content)

    print("-" * 40)
    print(f"INSTRUCTIONS:")
    print(f"1. Translate the above subtitle block to Simplified Chinese.")
    print(f"2. Tone: {style} (Verbalizer).")
    print(f"3. Apply Humanizer rules (No 'translationese').")
    print(f"4. Maintain strict ID/Time structure.")
    print(f"5. WRITE the result to: {chunk_path.replace('.srt', '.cn.srt')}")
    print("-" * 40)

    # In a real "Auto-Agent" loop, I would perform the translation here myself using my internal LLM.
    # But since I am running *inside* the python script, I cannot "think".
    # I must ask the External Agent (Me, the one typing this) to do it.

    translated_path = chunk_path.replace('.srt', '.cn.srt')

    # Wait for the file to exist
    while not os.path.exists(translated_path):
        time.sleep(2)

    print(f"✅ Chunk Completed: {translated_path}")
    return translated_path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_srt")
    parser.add_argument("--style", default="casual")
    parser.add_argument("--chunk-size", type=int, default=20)
    args = parser.parse_args()

    # 1. Split
    chunks_dir = os.path.join(os.path.dirname(args.input_srt), "chunks")
    if not os.path.exists(chunks_dir):
        srt_utils.split_to_chunks(args.input_srt, args.chunk_size, chunks_dir)

    chunks = sorted([os.path.join(chunks_dir, f) for f in os.listdir(chunks_dir) if f.endswith(".srt") and "chunk_" in f])

    # 2. Iterate and "Ask Agent"
    translated_files = []

    for chunk in chunks:
        # Check if already done
        cn_path = chunk.replace(".srt", ".cn.srt")
        if os.path.exists(cn_path):
            print(f"Skipping existing: {cn_path}")
            translated_files.append(cn_path)
            continue

        # Trigger Agent Action
        process_chunk_with_agent(chunk, args.style)
        translated_files.append(cn_path)

    # 3. Merge
    final_output = args.input_srt.replace(".srt", ".zh.srt")
    print(f"Merging {len(translated_files)} chunks to {final_output}...")
    srt_utils.merge_chunks(chunks_dir, final_output, pattern="chunk_*.cn.srt")
    print("Done!")

if __name__ == "__main__":
    main()