
import os
import re
import argparse
import sys

# Assume we are run from tools dir or similar, find STYLE_GUIDE relative
HARD_CONSTRAINTS_PATH = os.path.join(os.path.dirname(__file__), "..", "common", "HARD_CONSTRAINTS.md")

def load_regex_rules(filepath):
    rules = []
    if os.path.exists(filepath):
        print(f"Loading rules from: {filepath}")
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip non-table lines, separators, and headers
                if not line.startswith("|"): continue
                if re.match(r'^\|\s*:?-+:?\s*\|', line) or line.startswith("|---"): continue

                # Skip known headers
                lower = line.lower()
                if "| original" in lower or "| description" in lower or "| rule" in lower:
                    continue

                # Split by pipe, preserving empty strings (for empty replacements)
                # trim leading/trailing empty strings caused by outer pipes
                parts = re.split(r'(?<!\\)\|', line)

                # Clean up parts list
                if parts and not parts[0].strip(): parts.pop(0)  # Remove empty start
                if parts and not parts[-1].strip(): parts.pop()  # Remove empty end

                # Expecting: [Description, Pattern, Replacement, (Notes)]
                # So we need at least 3 parts: Desc, Pattern, Replacement
                if len(parts) >= 3:
                    # Extract columns
                    pattern = parts[1].strip()
                    replacement = parts[2].strip()

                    # Remove markdown code formatting
                    pattern = pattern.strip('`')
                    replacement = replacement.strip('`')

                    # Unescape pipes
                    pattern = pattern.replace(r'\|', '|')
                    replacement = replacement.replace(r'\|', '|')

                    if pattern:
                        rules.append((pattern, replacement))
    else:
        print(f"Warning: STYLE_GUIDE not found at {filepath}")
    return rules

REGEX_RULES = load_regex_rules(HARD_CONSTRAINTS_PATH)

def process_line(line):
    # Skip timestamp/index lines (simple heuristic)
    if re.match(r'^\d+$', line.strip()) or re.match(r'^\d{2}:\d{2}:\d{2},\d{3} -->', line.strip()):
        return line

    original = line
    # Apply Regex Rules
    text = line
    for pattern, replacement in REGEX_RULES:
        try:
            text = re.sub(pattern, replacement, text)
        except Exception as e:
            print(f"Regex error: {e} pattern={pattern}")

    # Fallback/Hardcoded cleanups (if not in MD)
    text = text.replace("此外，", "另外，")
    text = text.replace("总而言之，", "简单说，")

    # Trim
    text = re.sub(r'\s+', ' ', text).strip()

    # Preserve newline if it was stripped
    if original.endswith('\n'):
        text += '\n'

    return text

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file")
    args = parser.parse_args()

    input_path = os.path.abspath(args.input_file)
    if input_path.lower().endswith(".en.zh.srt"):
        output_path = input_path.replace(".en.zh.srt", ".zh.srt")
    else:
        output_path = input_path # Overwrite or rename? Let's overwrite safely
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_styled{ext}"

    print(f"Processing: {input_path}")

    with open(input_path, 'r', encoding='utf-8') as f_in, open(output_path, 'w', encoding='utf-8') as f_out:
        for line in f_in:
            f_out.write(process_line(line))

    print(f"✅ Saved cleaned file to: {output_path}")

if __name__ == "__main__":
    main()