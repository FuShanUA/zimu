import os
import sys
import argparse
import re
import yaml
from typing import List, Dict

# Setup paths for internal imports
CURRENT_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.dirname(CURRENT_SCRIPT_DIR)
PROJECT_ROOT = os.path.dirname(TOOLS_DIR)

sys.path.append(os.path.join(TOOLS_DIR, "common"))

try:
    import srt_utils
    import llm_utils
except ImportError as e:
    print(f"❌ Error: Required library not found: {e}")
    sys.exit(1)

# Default path configurations
TERMS_YML_PATH = os.path.join(TOOLS_DIR, "PostOS", "config", "terms.yml")
HARD_CONSTRAINTS_PATH = os.path.join(TOOLS_DIR, "common", "HARD_CONSTRAINTS.md")

def load_glossary_terms() -> List[str]:
    """Loads terms from terms.yml and returns them as a list of correct terms."""
    terms_list = []
    
    # 1. Load from terms.yml
    if os.path.exists(TERMS_YML_PATH):
        try:
            with open(TERMS_YML_PATH, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    for k, v in data.items():
                        # Extract both key and value if they are English proper nouns
                        if isinstance(k, str) and re.match(r'^[a-zA-Z0-9\s.\'-]+$', k.strip()):
                            terms_list.append(k.strip())
                        if isinstance(v, str) and re.match(r'^[a-zA-Z0-9\s.\'-]+$', v.strip()):
                            terms_list.append(v.strip())
        except Exception as e:
            print(f"⚠️ Failed to parse terms.yml: {e}")

    # 2. Add standard known proper nouns as a robust fallback
    known_fallbacks = ["Palantir"]
    for term in known_fallbacks:
        if term not in terms_list:
            terms_list.append(term)
            
    # Deduplicate and sort
    seen = set()
    unique_terms = []
    for term in terms_list:
        term_lower = term.lower()
        if term_lower not in seen and len(term) > 2:
            seen.add(term_lower)
            unique_terms.append(term)
            
    return unique_terms

def spellcheck_chunk(chunk_blocks: List[Dict], terms: List[str], client, model_name: str) -> List[Dict]:
    """Sends a chunk of subtitle blocks to Gemini to correct proper nouns based on context."""
    # Format input block
    input_text = ""
    for block in chunk_blocks:
        text = " ".join(block['lines']).replace("\n", " ").strip()
        input_text += f"[{block['index']}] {text}\n"

    terms_formatted = "\n".join([f"- {term}" for term in sorted(terms)])

    prompt = f"""You are an expert subtitle editor.
Your task is to review the following English subtitle transcript and perform **Strict Context-Aware Acoustic/Phonetic Spellchecking** on proper nouns, names, company names, or industry platforms.

### CRITICAL RULES TO PREVENT OVER-CORRECTION:
1. **Strict Phonetic/Acoustic Similarity**: Correct proper nouns ONLY if they sound almost identical to a glossary term (e.g., "Trey Stevens" -> "Trae Stephens", "Alex Carp" -> "Alex Karp"). Do NOT map different names or words.
2. **No Hallucination**: Never introduce names (like "Shyam" or "Shyam Sankar") out of thin air at the end of the blocks or anywhere else, unless there is a clear acoustically similar word (e.g. "Sean", "Shame") in the input block.
3. **No Over-Correction**: Do NOT replace correct proper nouns in the input with other glossary terms just because they are in the glossary. Specifically:
   - Do NOT change "Ondas" or similar words to "Anduril" (they are different companies/names).
   - Keep "Ondas" as "Ondas".
4. **No Translation**: Keep the text in English.
5. **No Style Alterations**: Do NOT rewrite general conversational phrases, change punctuation, or alter the sentence structure.
6. **Keep Original if Unsure**: If there is no clear acoustic mistake, keep the transcriber's text exactly as-is.

### CORRECT GLOSSARY TERMS & NAMES:
{terms_formatted}

### INPUT SUBTITLE BLOCKS:
{input_text}

### OUTPUT FORMAT:
Return ONLY the corrected subtitle blocks using the exact format `[ID] Text`. Do not add any introduction, explanations, or formatting.
Example:
[1] So I was chatting with Trae Stephens about Palantir.
[2] And Joe Lonsdale agreed.
"""

    try:
        # Use fallback=True to ensure robust cascading if Vertex/primary provider fails or model is unsupported
        response_text = client.generate_content(prompt, model_name=model_name, fallback=True)
        if not response_text:
            return chunk_blocks

        # Parse the output map
        corrected_map = {}
        for line in response_text.split('\n'):
            match = re.match(r'\[(\d+)\]\s*(.*)', line.strip())
            if match:
                idx = match.group(1)
                content = match.group(2).strip()
                if content:
                    corrected_map[idx] = content

        # Apply corrections back to blocks
        corrected_blocks = []
        for block in chunk_blocks:
            new_block = block.copy()
            idx = str(block['index'])
            if idx in corrected_map:
                # If there were multiple lines, split them back
                new_block['lines'] = [corrected_map[idx]]
            corrected_blocks.append(new_block)

        return corrected_blocks
    except Exception as e:
        print(f"⚠️ Error spellchecking chunk: {e}")
        return chunk_blocks  # Graceful fallback to original chunk

def run_spellcheck(srt_path: str, model_name: str = "gemini-3.1-flash-preview") -> bool:
    """Parses, spellchecks, and overwrites the target srt file."""
    if not os.path.exists(srt_path):
        print(f"❌ SRT file not found: {srt_path}")
        return False

    print(f"🎙️ Starting LLM Acoustic Spellcheck for: {os.path.basename(srt_path)}...")
    blocks = srt_utils.parse_srt(srt_path)
    if not blocks:
        print("⚠️ SRT file contains no valid blocks.")
        return False

    terms = load_glossary_terms()
    client = llm_utils.get_client()

    # Process in chunks of 60 blocks to optimize speed and context accuracy
    chunk_size = 60
    total_blocks = len(blocks)
    corrected_blocks = []

    print(f"   Loaded {len(terms)} terms. Processing {total_blocks} blocks in chunks of {chunk_size}...")

    for i in range(0, total_blocks, chunk_size):
        chunk = blocks[i:i + chunk_size]
        print(f"   -> Spellchecking blocks {i+1} to {min(i + chunk_size, total_blocks)}...")
        corrected_chunk = spellcheck_chunk(chunk, terms, client, model_name)
        corrected_blocks.extend(corrected_chunk)

    # Save corrected blocks back to SRT (subs first, then path)
    try:
        srt_utils.write_srt(corrected_blocks, srt_path)
        print("✅ LLM Acoustic Spellcheck completed successfully.")
        return True
    except Exception as e:
        print(f"❌ Failed to write spellchecked SRT file: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Context-Aware Acoustic/Phonetic Spellcheck for SRT files.")
    parser.add_argument("srt_path", help="Path to the SRT subtitle file to spellcheck.")
    parser.add_argument("--model", default="gemini-3.1-flash-preview", help="Gemini LLM model name.")
    args = parser.parse_args()

    success = run_spellcheck(args.srt_path, args.model)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
