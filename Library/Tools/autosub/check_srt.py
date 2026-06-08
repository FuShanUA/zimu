import re
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common'))

files = [
    r'/Users/shanfu/cc/Projects/Block CTO Dhanji Prasanna_ Building the AI-First Enterprise with Goose, their Open Source Agent/Block CTO Dhanji Prasanna： Building the AI-First Enterprise with Goose, their Open Source Agent [64J2lHxP0ok] [1080p].cn.srt',
    r'/Users/shanfu/cc/Projects/Inside Claude Code With Its Creator Boris Cherny/Inside Claude Code With Its Creator Boris Cherny [PQU9o_5rHC4].cn.srt'
]

import srt_utils

for f in files:
    print(f"\n--- Checking File: {f} ---")
    blocks = srt_utils.parse_srt(f)
    for i in range(len(blocks)):
        block = blocks[i]
        curr_text_joined = " ".join(block['lines'])

        # Scenario 1: Intra-block "。" followed by "，"
        match = re.search(r'。[”\"]?，', curr_text_joined)
        if match:
             print(f"[{block['index']}] INTRA-BLOCK: {curr_text_joined}")
             continue

        # Scenario 2: Previous block ended with "。" and this block starts with "，"
        if i > 0:
            prev_block = blocks[i-1]
            prev_text_joined = " ".join(prev_block['lines']).strip()
            curr_first_char = block['lines'][0].strip() if block['lines'] else ""

            if curr_first_char.startswith('，') and bool(re.search(r'。[”\"]?$', prev_text_joined)):
                 print(f"[{prev_block['index']}] PREV: {prev_text_joined}")
                 print(f"[{block['index']}] CURR: {curr_text_joined}\n")

        # Additional: just checking if current line starts with comma without previous ending in period. (already handled by rule A in auto-sub, but maybe missing?)
        if i > 0:
            prev_block = blocks[i-1]
            prev_text_joined = " ".join(prev_block['lines']).strip()
            curr_first_char = block['lines'][0].strip() if block['lines'] else ""
            if curr_first_char.startswith('，') and not bool(re.search(r'。[”\"]?$', prev_text_joined)):
                 print(f"[{prev_block['index']}] PREV (No Period): {prev_text_joined}")
                 print(f"[{block['index']}] CURR: {curr_text_joined}\n")