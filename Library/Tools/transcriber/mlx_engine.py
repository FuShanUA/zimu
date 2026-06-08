import os
import sys
import json
import time

try:
    import mlx_whisper
    HAS_MLX = True
except ImportError:
    HAS_MLX = False

class MLXSegment:
    def __init__(self, start, end, text, words=None):
        self.start = start
        self.end = end
        self.text = text
        self.words = words or []

def transcribe_mlx(file_path, model_name="large-v2", initial_prompt=None, clip_timestamps=None, total_duration=0, checkpoint_path=None):
    """
    Transcribe using mlx-whisper for Apple Silicon GPU acceleration.
    """
    if not HAS_MLX:
        raise ImportError("mlx-whisper not installed")

    # Optimizing Memory and VRAM allocation on Mac: disable hoarding cache
    try:
        import mlx.core as mx
        mx.set_cache_limit(0)
        mx.clear_cache()
        print(f"⚙️ [MLX Memory Optimizer] Set GPU allocation cache limit to 0 and cleared cache.", flush=True)
    except Exception as e:
        print(f"⚠️ [MLX Memory Optimizer] Warning: failed to configure cache limit: {e}", flush=True)

    print(f"🚀 [MLX Mode] Using Apple Silicon GPU acceleration...", flush=True)

    # Resolve Hugging Face Repo Name accurately
    if "/" in model_name:
        path_or_hf_repo = model_name
    else:
        m_lower = model_name.lower().strip()
        if m_lower == "turbo":
            path_or_hf_repo = "mlx-community/whisper-large-v3-turbo"
        elif m_lower == "large-v3-turbo":
            path_or_hf_repo = "mlx-community/whisper-large-v3-turbo"
        elif m_lower in ["tiny", "base", "small", "medium"]:
            path_or_hf_repo = f"mlx-community/whisper-{m_lower}"
        elif m_lower in ["large", "large-v1", "large-v2", "large-v3"]:
            path_or_hf_repo = f"mlx-community/whisper-{m_lower}-mlx"
        else:
            path_or_hf_repo = f"mlx-community/whisper-{model_name}-mlx"

    kwargs = {
        "path_or_hf_repo": path_or_hf_repo,
        "initial_prompt": initial_prompt,
        "verbose": True,  # Set verbose to True to print segments to stdout in real-time
        "word_timestamps": True
    }
    
    if clip_timestamps:
        # clip_timestamps can be [start, end]
        # Safety: subtract a tiny bit from end to avoid MLX hanging bug
        start, end = clip_timestamps
        kwargs["clip_timestamps"] = [float(start), max(float(start), float(end) - 0.1)]

    # Real-time stdout interception to extract segments and print progress
    import re
    checkpoint_segments = []
    if checkpoint_path and os.path.exists(checkpoint_path):
        try:
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                checkpoint_segments = json.load(f).get('segments', [])
        except:
            pass

    original_stdout = sys.stdout
    # Pattern to match: [MM:SS.mmm --> MM:SS.mmm] text or [HH:MM:SS.mmm --> HH:MM:SS.mmm] text
    pattern = re.compile(r"^\[(?:(\d{2}):)?(\d{2}):(\d{2})\.(\d{3}) --> (?:(\d{2}):)?(\d{2}):(\d{2})\.(\d{3})\] (.*)")

    def parse_timestamp(h_str, m_str, s_str, ms_str):
        h = int(h_str) if h_str else 0
        m = int(m_str)
        s = int(s_str)
        ms = int(ms_str)
        return h * 3600 + m * 60 + s + ms / 1000.0

    def handle_line(line):
        line_strip = line.strip()
        m = pattern.match(line_strip)
        if m:
            start_time = parse_timestamp(m.group(1), m.group(2), m.group(3), m.group(4))
            end_time = parse_timestamp(m.group(5), m.group(6), m.group(7), m.group(8))
            text = m.group(9)

            # Reconstruct segment dict for real-time checkpointing
            seg_dict = {
                'start': start_time,
                'end': end_time,
                'text': text,
                'words': []
            }
            checkpoint_segments.append(seg_dict)
            
            if checkpoint_path:
                temp_path = checkpoint_path + ".tmp"
                try:
                    with open(temp_path, 'w', encoding='utf-8') as f:
                        json.dump({'segments': checkpoint_segments}, f, ensure_ascii=False, indent=2)
                    os.replace(temp_path, checkpoint_path)
                except Exception:
                    pass

            if total_duration > 0:
                p = round((end_time / total_duration) * 100, 1)
                original_stdout.write(f"Progress: {p}% ({end_time:.0f}/{total_duration:.0f}s)\n")
                original_stdout.flush()
        else:
            # Forward other prints to real stdout
            original_stdout.write(line + "\n")
            original_stdout.flush()

    class StdoutRedirector:
        def __init__(self):
            self.buffer = ""

        def write(self, s):
            self.buffer += s
            while "\n" in self.buffer:
                line, self.buffer = self.buffer.split("\n", 1)
                handle_line(line)

        def flush(self):
            original_stdout.flush()

    sys.stdout = StdoutRedirector()
    try:
        # mlx-whisper.transcribe returns a dict: {"text": "...", "segments": [...]}
        result = mlx_whisper.transcribe(file_path, **kwargs)
    finally:
        sys.stdout = original_stdout

    segments = result.get("segments", [])
    for s in segments:
        words = []
        if "words" in s:
            for w in s["words"]:
                # Normalize word format to match faster-whisper (getattr compatible)
                words.append(type('Word', (), {'start': w['start'], 'end': w['end'], 'word': w['word'], 'probability': w.get('probability', 0)}))
        
        yield MLXSegment(s["start"], s["end"], s["text"], words=words)

    # Clean up and release Metal allocations back to OS immediately
    try:
        import mlx.core as mx
        mx.clear_cache()
        print(f"🧹 [MLX Memory Optimizer] Cleared Metal allocation cache upon completion.", flush=True)
    except:
        pass

def is_apple_silicon():
    if sys.platform != "darwin": return False
    # Use sysctl to check for arm64
    try:
        import subprocess
        output = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"]).decode("utf-8").lower()
        return "apple" in output
    except:
        return False
