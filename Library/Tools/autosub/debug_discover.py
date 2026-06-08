import os, re

def find_local_file(workdir, extensions, pattern=None, exclude_pattern=None):
    if not workdir or not os.path.exists(workdir): return None
    try:
        files = os.listdir(workdir)
        matches = [f for f in files if os.path.splitext(f)[1].lower() in extensions]
        if pattern:
            matches = [f for f in matches if re.search(pattern, f)]
        if exclude_pattern:
            matches = [f for f in matches if not re.search(exclude_pattern, f)]
        
        if not matches: return None
        if any(ext in ['.mp4', '.mkv', '.webm'] for ext in extensions):
            matches.sort(key=lambda x: os.path.getsize(os.path.join(workdir, x)), reverse=True)
        else:
            matches.sort(key=lambda x: os.path.getmtime(os.path.join(workdir, x)), reverse=True)
        return os.path.join(workdir, matches[0])
    except Exception as e:
        return str(e)

def discover_stage(workdir):
    if not workdir or not os.path.exists(workdir): return "DL"
    if find_local_file(workdir, ['.mp4', '.mkv'], pattern=r'_hardsub'): return "DONE"
    if find_local_file(workdir, ['.srt'], pattern=r'\.bi\.srt$'): return "BR"
    if find_local_file(workdir, ['.srt'], pattern=r'(\.zh|\.cn)\.srt$'): return "MR"
    if find_local_file(workdir, ['.srt'], exclude_pattern=r'(\.zh|\.cn|\.bi)\.srt$'): return "TL"
    if find_local_file(workdir, ['.mp4', '.mkv', '.webm']): return "TR"
    return "DL"

workdir = r"d:\cc\Projects\Speaking_of_Data_Podcast\01_Automation with AI Agents_HzGvShJOQ64"
print(f"Testing workdir: {workdir}")
print(f"Files: {os.listdir(workdir)}")
stage = discover_stage(workdir)
print(f"Discovered Stage: {stage}")

# Extra check for the source SRT
srt = find_local_file(workdir, ['.srt'], exclude_pattern=r'(\.zh|\.cn|\.bi)\.srt$')
print(f"Source SRT found: {srt}")
