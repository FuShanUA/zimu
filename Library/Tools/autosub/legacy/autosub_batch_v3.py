import os
import sys
import re
import time
import json
import threading
import queue
import subprocess
import argparse
from datetime import datetime

# --- Global Window Suppression Patch for Windows ---
if sys.platform == "win32":
    _original_popen = subprocess.Popen
    def _patched_popen(*args, **kwargs):
        cflags = kwargs.get('creationflags', 0)
        # Safe access to CREATE_NO_WINDOW for linters on Mac
        CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        kwargs['creationflags'] = cflags | CREATE_NO_WINDOW
        return _original_popen(*args, **kwargs)
    subprocess.Popen = _patched_popen
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.align import Align
from rich.text import Text
from rich import box
import psutil

# --- Configuration & Paths ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.dirname(CURRENT_DIR)
PROJECT_ROOT = os.path.dirname(TOOLS_DIR)
DOWNLOAD_ROOT = os.path.join(PROJECT_ROOT, "Projects")

VDOWN_CMD = [sys.executable, os.path.join(TOOLS_DIR, "vdown", "download.py")]
TRANSCRIBER_CMD = [sys.executable, os.path.join(TOOLS_DIR, "transcriber", "transcribe_engine.py")]
SMART_TRANSLATE_CMD = [sys.executable, os.path.join(TOOLS_DIR, "autosub", "smart_translate.py")]
SUBTRANSLATOR_CMD = [sys.executable, os.path.join(TOOLS_DIR, "subtranslator", "subtranslator.py")]
SRT2ASS_CMD = [sys.executable, os.path.join(TOOLS_DIR, "hardsubber", "srt_to_ass.py")]
BURNSUB_CMD = [sys.executable, os.path.join(TOOLS_DIR, "hardsubber", "burn_engine.py")]
# --- Robust Tool Detection ---
def get_tool_path(tool_name="ffmpeg"):
    import shutil
    import glob
    # 1. Check PATH
    path = shutil.which(tool_name)
    if path: return path

    # 2. Check WinGet Gyan Tool (User Specific)
    user_home = os.path.expanduser("~")
    winget_base = os.path.join(user_home, "AppData", "Local", "Microsoft", "Winget", "Packages")
    if os.path.exists(winget_base):
        for d in os.listdir(winget_base):
            if tool_name in d:
                for bin_dir in glob.glob(os.path.join(winget_base, d, "**/bin"), recursive=True):
                    tool_path = os.path.join(bin_dir, f"{tool_name}.exe")
                    if os.path.exists(tool_path): return tool_path

    # 3. Check common hardcoded paths
    fallbacks = [
        r"C:\ffmpeg\bin",
        r"C:\Program Files\ffmpeg\bin",
        r"D:\Program Files\CapCut\7.7.0.3143",
    ]
    for fb in fallbacks:
        p = os.path.join(fb, f"{tool_name}.exe")
        if os.path.exists(p): return p

    return tool_name # Default fallback

FFMPEG_EXE = get_tool_path("ffmpeg")
FFPROBE_EXE = get_tool_path("ffprobe")

# Helper for Process Management
class ProcessTree:
    @staticmethod
    def suspend(pid):
        if not pid: return
        try:
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                try: child.suspend()
                except: pass
            parent.suspend()
        except psutil.NoSuchProcess: pass
        except Exception as e:
            pass

    @staticmethod
    def kill(pid):
        if not pid: return
        try:
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                try: child.kill()
                except: pass
            parent.kill()
        except psutil.NoSuchProcess: pass
        except Exception as e: pass

    @staticmethod
    def suspend(pid):
        if not pid: return
        try:
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                try: child.suspend()
                except: pass
            parent.suspend()
        except psutil.NoSuchProcess: pass
        except Exception as e: pass

    @staticmethod
    def resume(pid):
        if not pid: return
        try:
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                try: child.resume()
                except: pass
            parent.resume()
        except psutil.NoSuchProcess: pass
        except Exception as e:
            pass

# --- Data Models ---
class SubtitleTask:
    def __init__(self, uid, url, title):
        self.uid = uid
        self.url = url
        self.title = title or "Unknown"
        self.status = "QUEUED"
        self.pcts = {"DL": 0.0, "TR": 0.0, "TL": 0.0, "MR": 0.0, "BR": 0.0}
        self.error = None
        self.pid = None
        self.created_at = time.time()
        self.finished_at = None
        self.is_manual_paused = False
        self.is_manual_restarted = False
        self.workdir = None
        self.vid_id = self.extract_id(url)

    @staticmethod
    def extract_id(url):
        if not url: return None
        # Handle YouTube URLs
        if "youtube.com" in url or "youtu.be" in url:
            m = re.search(r'(?:v=|\/|v\/|embed\/|watch\?v=|\&v=)([0-9A-Za-z_-]{11}).*', url)
            if m: return m.group(1)
        # Generic: take last 11 chars as fallback
        return url[-11:]

    @property
    def display_title(self):
        t = self.title
        if t == "Unknown" and self.workdir:
             # Try extract title from folder name prefix XX_Title_ID
             folder_name = os.path.basename(self.workdir)
             m = re.search(r'^\d{2}_(.*)(?:_[0-9A-Za-z_-]{11}| \[[0-9A-Za-z_-]{11}\])', folder_name)
             if m: t = m.group(1).replace("_", " ").strip()
             elif "_" in folder_name: t = folder_name.split("_")[1].strip()

        if self.vid_id and self.vid_id not in t:
             t = f"{t} [{self.vid_id}]"
        return (t[:45] + "..") if len(t) > 45 else t

    def get_zh_status(self):
        """Returns a color-coded status string for the TUI."""
        if getattr(self, 'is_manual_paused', False):
            return "[yellow]暂停[/yellow]"

        if "DONE" in self.status:
            return "[green]完成[/green]"
        if "FAILED" in self.status:
            return "[red]处理失败[/red]"
        if "ACTIVE" in self.status:
            return "[bright_blue]进行中[/bright_blue]"
        if "QUEUED" in self.status:
            return "[grey30]排队中[/grey30]"
        if "SKIPPED" in self.status:
            return "[dim]已跳过[/dim]"
        return f"[white]{self.status}[/white]"

    def set_status(self, s: str):
        self.status = s
        if s in ["DONE", "FAILED", "SKIPPED"]:
            self.finished_at = time.time()
            self.pid = None

    def update_pct(self, stage: str, val: float):
        self.pcts[stage] = val

    def is_active(self, stage: str):
        """Returns True if the specified stage is currently active."""
        if "(" + stage + ")" in self.status: return True
        if stage == "BR" and "BR_" in self.status: return True
        return False

    def get_br_pct(self):
        """Returns the composite progress of the Burn stage."""
        return max(self.pcts.get("BR") or 0.0, self.pcts.get("BR_ASS") or 0.0, self.pcts.get("BR_BURN") or 0.0)

    def to_dict(self):
        d = self.__dict__.copy()
        d['pid'] = None # Don't persist PIDs across sessions
        d['is_manual_paused'] = False # Reset pause on save/load
        return d

    @classmethod
    def from_dict(cls, d):
        t = cls(d['uid'], d['url'], d['title'])
        t.status = d.get('status', 'QUEUED')
        t.pcts = d.get('pcts', {"DL": 0.0, "TR": 0.0, "TL": 0.0, "MR": 0.0, "BR": 0.0})
        t.error = d.get('error')
        t.created_at = d.get('created_at', time.time())
        t.finished_at = d.get('finished_at')
        t.is_manual_paused = d.get('is_manual_paused', False)
        t.is_manual_restarted = d.get('is_manual_restarted', False)
        t.workdir = d.get('workdir')
        t.vid_id = d.get('vid_id', t.extract_id(t.url))
        return t

# --- Pipeline Engine ---
class PipelineManager:
    def __init__(self, args):
        self.args = args
        self.task_map = {}
        self.url_map = {}
        self.active_uids = set()
        self.lock = threading.RLock()
        self.global_abort = False
        self.global_pause = threading.Event()
        self.global_pause.set() # Default: Run

        self.task_limit = getattr(args, 'max_tasks', 4)
        self.task_semaphore = threading.Semaphore(self.task_limit)

        # Staged Concurrency (Compute-heavy vs API-heavy vs IO-heavy)
        self.tr_semaphore = threading.Semaphore(4)      # Transcription (Whisper) - Concurrent 4
        self.br_semaphore = threading.Semaphore(4)      # Burning (FFmpeg) - Concurrent 4
        self.io_semaphore = threading.Semaphore(4)      # DL, MR - Increased to 4
        self.api_semaphore = threading.Semaphore(20)    # Global LLM API pool - Concurrent 20

        self.queues = {
            "DL": queue.Queue(),
            "TR": queue.Queue(),
            "TL": queue.Queue(),
            "MR": queue.Queue(),
            "BR": queue.Queue()
        }

        self.state_path = getattr(args, 'state_file', "autosub_batch_state.json")
        # Ensure command file is in the same directory as state file
        project_dir = os.path.dirname(os.path.abspath(self.state_path))
        self.cmd_path = os.path.join(project_dir, "autosub_batch_cmd.json")
        self.is_watcher = getattr(args, 'status', False)
        self.silent_mode = getattr(args, 'silent', False)

        self.log_file = None
        log_dir = os.path.dirname(os.path.abspath(self.state_path)) if self.state_path else self.args.output_dir
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            self.log_file = open(os.path.join(log_dir, "autosub_batch.log"), "a", encoding="utf-8")

        # Proactive FFPROBE check
        import shutil
        self.ffprobe = shutil.which("ffprobe") or "ffprobe"

    def log(self, msg: str):
        if self.log_file:
            # Avoid stripping [DL], [TR] etc. by only targeting Rich bracket styles if needed
            # For now, let's just use a more selective regex or skip stripping in file log
            clean_msg = re.sub(r"\[(bold|cyan|green|red|yellow|white|bright_blue|grey30|dim|/.*?)\]", "", msg)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            self.log_file.write(f"[{timestamp}] {clean_msg}\n")
            self.log_file.flush()
        if not self.is_watcher and not self.silent_mode:
            print(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def _get_semaphore(self, stage: str):
        """Maps a stage string to the appropriate concurrency semaphore."""
        if not stage: return self.task_semaphore
        prefix = stage.split("_")[0] if "_" in stage else stage
        if prefix == "TR":
            return self.tr_semaphore
        if prefix == "BR":
            return self.br_semaphore
        if prefix in ["DL", "MR"]:
            return self.io_semaphore
        if prefix == "TL":
            return self.api_semaphore
        return self.task_semaphore

    def acquire_slot(self, task: SubtitleTask, stage: str):
        """Acquires a stage-specific concurrency slot."""
        with self.lock:
            if task.uid in self.active_uids:
                return True

        sem = self._get_semaphore(stage)
        sem.acquire()

        with self.lock:
            self.active_uids.add(task.uid)
            task.set_status(f"ACTIVE ({stage})")
        return True

    def release_slot(self, task: SubtitleTask, stage: Optional[str] = None):
        """Releases a stage-specific concurrency slot."""
        with self.lock:
            if task.uid not in self.active_uids:
                return
            self.active_uids.remove(task.uid)

        sem = self._get_semaphore(stage)
        try:
            sem.release()
            self.log(f"任务 {task.uid} 已从 {stage or 'GLOBAL'} 环境退出. (当前活跃: {len(self.active_uids)})")
        except ValueError:
            pass # In case of double release

    def shutdown(self):
        """Kill all active processes and save state."""
        self.log("\n[SYSTEM] ATTENTION: Shutting down all active tasks...")
        self.global_abort = True
        with self.lock:
            uids = list(self.active_uids)

        for uid in uids:
            t = self.task_map.get(uid)
            if t and t.pid:
                self.log(f"Killing process {t.pid} for Task {uid}...")
                ProcessTree.kill(t.pid)

        self.save_state(force=True)

    def get_video_dimensions(self, path):
        try:
            # Shield path in quotes if calling via string logic, but list is better
            # Safe access to CREATE_NO_WINDOW for linters on Mac
            CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            cmd = [FFPROBE_EXE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", os.path.abspath(path)]
            out = subprocess.check_output(cmd, creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0).decode().strip()
            if "x" in out:
                w, h = out.split("x")
                return int(w), int(h)
        except Exception as e:
            self.log(f"FFprobe Warning for {os.path.basename(path)}: {e}")
        return 1920, 1080

    def find_local_file(self, workdir, extensions, pattern=None, exclude_pattern=None):
        """Robustly find a file in the workdir by extensions and optional regex pattern."""
        if not workdir or not os.path.exists(workdir): return None
        try:
            files = os.listdir(workdir)
            matches = [f for f in files if os.path.splitext(f)[1].lower() in extensions]
            if pattern:
                matches = [f for f in matches if re.search(pattern, f)]
            if exclude_pattern:
                matches = [f for f in matches if not re.search(exclude_pattern, f)]

            if not matches: return None
            # Return either the largest (for videos) or newest file
            if any(ext in ['.mp4', '.mkv', '.webm'] for ext in extensions):
                matches.sort(key=lambda x: os.path.getsize(os.path.join(workdir, x)), reverse=True)
            else:
                matches.sort(key=lambda x: os.path.getmtime(os.path.join(workdir, x)), reverse=True)
            return os.path.join(workdir, matches[0])
        except: return None

    def get_video_duration(self, video_path):
        """Returns video duration in seconds using ffprobe."""
        if not video_path or not os.path.exists(video_path):
            return 0.0
        try:
            cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode().strip()
            return float(output)
        except:
            return 0.0

    def discover_stage(self, workdir):
        """Scans the workdir to determine the furthest stage reached (Disk Truth)."""
        if not workdir or not os.path.exists(workdir):
            return "DL"

        # Helper to check if file is non-empty and exists
        def is_valid(path, min_size=100):
            return path and os.path.exists(path) and os.path.getsize(path) >= min_size

        # 1. Verification Logic: Compare Hardsub vs Raw Source
        final_mp4 = self.find_local_file(workdir, ['.mp4', '.mkv'], pattern=r'_hardsub')
        raw_vid = self.find_local_file(workdir, ['.mp4', '.mkv', '.webm'], exclude_pattern=r'_hardsub')

        if is_valid(final_mp4, 1024*1024):
            if is_valid(raw_vid):
                # Critical Check: Verify duration matches
                h_dur = self.get_video_duration(final_mp4)
                r_dur = self.get_video_duration(raw_vid)
                if abs(h_dur - r_dur) < 5.0 and h_dur > 0:
                    return "DONE"
                else:
                    self.log(f"Hardsub duration mismatch ({h_dur:.1f}s vs {r_dur:.1f}s) for {workdir}. Re-burning required.")
                    return "BR"
            else:
                # If raw video is missing, we can't verify. Assume BR to be safe if a hardsub was attempted.
                return "BR"

        # 2. Check for bilingual SRT
        bi_srt = self.find_local_file(workdir, ['.srt'], pattern=r'\.bi\.srt$')
        if is_valid(bi_srt, 1024):
            return "BR"

        # 3. Check for CN/ZH SRT
        cn_srt = self.find_local_file(workdir, ['.srt'], pattern=r'(\.cn|\.zh)\.srt$')
        if is_valid(cn_srt, 1024):
            return "MR"

        # 4. Check for source SRT
        en_srt = self.find_local_file(workdir, ['.srt'], exclude_pattern=r'(\.zh|\.cn|\.bi)\.srt$')
        if is_valid(en_srt):
            return "TL"

        # 5. Check for raw video (Download ready -> Proceed to Transcription)
        if is_valid(raw_vid, 1024*1024):
            return "TR"

        return "DL"

    def save_state(self, force=False):
        if self.is_watcher: return
        with self.lock:
            if not self.task_map and os.path.exists(self.state_path) and not force:
                return # Safety: Don't overwrite if we lost tasks in RAM
            data = {
                "tasks": [t.to_dict() for t in self.task_map.values()],
                "global_pause": not self.global_pause.is_set(),
                "last_update": time.time()
            }
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"Error saving state: {e}")

    def load_state(self):
        self.log(f"Attempting to load state from {self.state_path}")
        if not os.path.exists(self.state_path):
            self.log("State file not found.")
            return False
        for attempt in range(5):
            try:
                # Use utf-8-sig to handle PowerShell's BOM
                with open(self.state_path, "r", encoding="utf-8-sig") as f:
                    state = json.load(f)

                with self.lock:
                    # User requested: Reset pause state on restart
                    if not self.is_watcher:
                        self.global_pause.set() # ALWAYS unpause Master on load
                    else:
                        # Watcher stays in sync with Master if it reads state
                        if state.get("global_pause", False):
                            self.global_pause.clear()
                        else:
                            self.global_pause.set()

                    tasks_loaded = 0
                    queues_populated = 0
                    for t_dict in state.get("tasks", []):
                        t = SubtitleTask.from_dict(t_dict)
                        t.is_manual_paused = False # Always reset manual pause on load
                        self.task_map[t.uid] = t
                        self.url_map[t.url] = t
                        tasks_loaded += 1

                        if not self.is_watcher:
                            # PROACTIVE SELF-HEALING: Always check disk if status is not DONE
                            found_stage = self.discover_stage(t.workdir)

                            # Force DONE if hardsub exists on disk
                            if found_stage == "DONE":
                                if t.status != "DONE":
                                    self.log(f"Recovered DONE task via disk discovery: {t.uid}")
                                t.set_status("DONE")
                                for s in ["DL", "TR", "TL", "MR", "BR"]: t.pcts[s] = 100.0
                            else:
                                # Not DONE on disk - needs queuing
                                should_requeue = False

                                # Disk-First Truth Reset:
                                # If disk says we are at an early stage, reset JSON pcts for logic consistency
                                stage_order = ["DL", "TR", "TL", "MR", "BR"]
                                try:
                                    actual_idx = stage_order.index(found_stage)
                                    for idx, s in enumerate(stage_order):
                                        if idx > actual_idx:
                                            if (t.pcts.get(s) or 0.0) > 0:
                                                self.log(f"Self-Healing: Resetting {s} progress for Task {t.uid} (Disk is at {found_stage})")
                                                t.update_pct(s, 0.0)
                                except:
                                    pass

                                if found_stage == "DONE":
                                    t.update_pct("BR", 100.0)
                                    t.set_status("DONE")
                                    continue

                                if t.status == "DONE":
                                    # [REFINED] Disk-First Truth: If disk says it's not done, it's not done.
                                    self.log(f"Disk Truth mismatch: Task {t.uid} was DONE in JSON but is only at {found_stage} on disk. Resuming...")
                                    should_requeue = True
                                elif t.status == "FAILED":
                                    self.log(f"Re-activating FAILED Task {t.uid} from JSON state.")
                                    should_requeue = True
                                elif t.status not in ["SKIPPED"]:
                                    should_requeue = True

                                if t.status == "QUEUED":
                                    should_requeue = True

                                # ALWAYS RE-QUEUE IF DISK IS NOT DONE (Disk wins over JSON)
                                if found_stage != "DONE":
                                    should_requeue = True

                                if should_requeue:
                                    t.set_status("QUEUED")
                                    target_q = "DL"
                                    if found_stage in self.queues: target_q = found_stage

                                    self.log(f"RE-QUEUING Task {t.uid} to stage {target_q}...")
                                    self.queues[target_q].put(t)
                                    queues_populated += 1

                                    # Auto-fill previous stage progress
                                    stages_list = ["DL", "TR", "TL", "MR", "BR"]
                                    if target_q in stages_list:
                                        idx = stages_list.index(target_q)
                                        # Set previous to 100%
                                        for i in range(idx): t.pcts[stages_list[i]] = 100.0
                                        # Reset downstream to 0% to fix TUI display (e.g. Task 15)
                                        for i in range(idx, len(stages_list)):
                                            t.pcts[stages_list[i]] = 0.0
                                            # Sub-stages too
                                            if stages_list[i] == "BR":
                                                t.pcts["BR_ASS"] = 0.0
                                                t.pcts["BR_BURN"] = 0.0

                    self.log(f"Successfully loaded {tasks_loaded} tasks, re-queued {queues_populated} active tasks.")
                    if not self.is_watcher:
                        self.save_state(force=True)
                return True
            except Exception as e:
                self.log(f"Failed to load state after {attempt+1} attempts: {e}")
                time.sleep(1)
        return False

    def handle_external_commands(self):
        if not os.path.exists(self.cmd_path): return
        try:
            # Use utf-8-sig to handle PowerShell's BOM
            with open(self.cmd_path, "r", encoding="utf-8-sig") as f:
                cmds = json.load(f)

            if not isinstance(cmds, list): cmds = [cmds]

            for c in cmds:
                uid = c.get("uid")
                cmd_type = c.get("type")

                # GLOBAL COMMANDS
                if uid is None:
                    if cmd_type == "terminate":
                        self.log("RECEIVED GLOBAL TERMINATE - Shutting down master...")
                        self.global_abort = True
                    elif cmd_type == "pause_all":
                        if self.global_pause.is_set():
                            self.global_pause.clear()
                            with self.lock:
                                for tid in list(self.active_uids):
                                    t = self.task_map.get(tid)
                                    if t and t.pid: ProcessTree.suspend(t.pid)
                    elif cmd_type == "resume_all":
                        if not self.global_pause.is_set():
                            self.global_pause.set()
                            with self.lock:
                                for tid in list(self.active_uids):
                                    t = self.task_map.get(tid)
                                    if t and t.pid: ProcessTree.resume(t.pid)
                    continue

                if uid and uid in self.task_map:
                    if cmd_type == "pause": self.toggle_task_pause(uid)
                    elif cmd_type == "restart": self.restart_task(uid)

            # Delete after handling ALL commands
            if os.path.exists(self.cmd_path):
                os.remove(self.cmd_path)
        except Exception as e:
            self.log(f"Error handling external commands: {e}")

    def send_cmd(self, uid, cmd_type):
        """Send command to master via file (for Watcher mode)."""
        cmds = []
        if os.path.exists(self.cmd_path):
            try:
                # Use utf-8-sig for reliability
                with open(self.cmd_path, "r", encoding="utf-8-sig") as f:
                    cmds = json.load(f)
                    if not isinstance(cmds, list): cmds = [cmds]
            except: cmds = []

        cmds.append({"uid": uid, "type": cmd_type, "time": time.time()})
        with open(self.cmd_path, "w", encoding="utf-8") as f:
            json.dump(cmds, f, indent=2)

    def toggle_task_pause(self, uid):
        task = self.task_map.get(uid)
        if not task: return
        with self.lock:
            if task.is_manual_paused:
                task.is_manual_paused = False
                self.log(f"任务 {uid} 已继续")
                # Resume process
                if task.pid: ProcessTree.resume(task.pid)
            else:
                task.is_manual_paused = True
                self.log(f"任务 {uid} 已暂停")
                # Suspend process
                if task.pid: ProcessTree.suspend(task.pid)

    def restart_task(self, uid):
        task = self.task_map.get(uid)
        if not task: return
        with self.lock:
            # First, kill any existing process tree
            if task.pid:
                ProcessTree.kill(task.pid)
                task.pid = None

            # Wipe progress for all stages (will be refilled by discover_stage)
            task.pcts = {"DL": 0.0, "TR": 0.0, "TL": 0.0, "MR": 0.0, "BR": 0.0}
            task.set_status("QUEUED")

            # Put back in DL queue; discover_stage will warp it to the correct point
            task.error = None
            self.queues["DL"].put(task)
            self.log(f"任务 {uid} 已成功重置并加入队列")
            self.save_state(force=True)

    def add_task(self, url: str, title: Optional[str] = None):
        with self.lock:
            if url in self.url_map:
                return self.url_map[url]

            uid = len(self.task_map) + 1
            task = SubtitleTask(uid, url, title)
            self.task_map[uid] = task
            self.url_map[url] = task

            self.queues["DL"].put(task)
        return task

    def run_cmd(self, task, cmd, stage, is_api_heavy=False):
        """Runs a command as a subprocess and streams progress updates."""
        if self.global_abort: return False
        task.set_status(f"WAIT ({stage})")

        # NOTE: acquire_slot ALREADY handles the stage-specific semaphore (including API for TL).
        # We only call it here to manage the ACTIVE status and concurrency slots.
        # IF the stage is NOT TL but IS api_heavy, we might need a separate API slot?
        # But for now, we just rely on acquire_slot.
        self.acquire_slot(task, stage)
        error_buffer = []
        project_log_path = os.path.join(task.workdir, f"task_{task.uid}_{stage}.log") if task.workdir else None

        try:
            p = None
            cwd = task.workdir if task.workdir and os.path.exists(task.workdir) else None
            # Status is set to ACTIVE inside acquire_slot
            self.log(f"Starting {stage} for task {task.uid} ({task.display_title})")

            p = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=cwd,
                env=os.environ,
                encoding='utf-8',
                errors='replace',
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == "win32" else 0
            )
            task.pid = p.pid
            self.log(f"Process {task.pid} started for task {task.uid}")

            # Subprocess output loop
            if p.stdout:
                for line in p.stdout:
                if self.global_abort:
                    self.log(f"GLOBAL ABORT detected - Killing PID {p.pid} for Task {task.uid}")
                    ProcessTree.kill(p.pid)
                    break

                line = line.strip()
                if not line: continue

                if project_log_path:
                    with open(project_log_path, "a", encoding="utf-8") as f:
                        f.write(line + "\n")

                error_buffer.append(line)
                if len(error_buffer) > 10: error_buffer.pop(0)

                percent = None
                if "Progress:" in line:
                    m = re.search(r'Progress:\s*([\d\.]+)%', line)
                    if m: percent = float(m.group(1))
                elif "[download]" in line and "%" in line:
                    m = re.search(r'\[download\]\s*([\d\.]+)%', line)
                    if m: percent = float(m.group(1))

                if percent is not None:
                    task.update_pct(stage, percent)

            p.wait()
            ret = p.returncode
            task.pid = None

            # If the task was restarted while running, the status will be WAITING
            if task.status == "WAITING":
                return False

            if ret != 0:
                meaningful_error = "Unknown Error"
                for line in reversed(error_buffer):
                    if "ERROR:" in line or "error" in line.lower() or "Sign in" in line:
                        meaningful_error = line
                        break
                else:
                    if error_buffer: meaningful_error = error_buffer[-1]
                task.error = meaningful_error
                task.set_status("FAILED")
                self.log(f"FAILED {stage} for task {task.uid}: {meaningful_error}")
                return False

            task.update_pct(stage, 100.0)
            self.log(f"COMPLETED {stage} for task {task.uid}")
            return True
        except Exception as e:
            task.error = str(e)
            if stage == "TL":
                # API Calls don't need a heavy WAITING label typically as they are many, but let's be consistent
                task.set_status(f"WAIT ({stage})")
            else:
                task.set_status(f"WAIT ({stage})")
            self.log(f"EXCEPTION in {stage} for task {task.uid}: {e}")
            return False
        finally:
            self.release_slot(task, stage)
            if p and p.stdout:
                p.stdout.close()
                p.wait()

    def dl_worker(self):
        self.log("Worker thread [DL] started")
        while not self.global_abort:
            self.global_pause.wait()
            task = None
            try:
                task = self.queues["DL"].get(timeout=1)
                self.log(f"DL Worker picked up Task {task.uid}")

                if task.is_manual_paused or task.status == "DONE":
                    self.queues["DL"].task_done()
                    continue

                # Slots are handled inside run_cmd for each substage
                # DISCOVERY: Warp to furthest stage if files exist
                    # Determine workdir if not set
                    vid_id = task.vid_id
                    # Try to find existing folder in output_dir
                    found = False
                    for d in os.listdir(self.args.output_dir):
                        if vid_id and vid_id in d and os.path.isdir(os.path.join(self.args.output_dir, d)):
                            task.workdir = os.path.join(self.args.output_dir, d)
                            found = True
                            break
                    if not found:
                        safe_title = re.sub(r'[\\/*?:"<>|]', '_', task.title).strip()
                        folder_name = f"{safe_title} [{vid_id}]" if vid_id else f"temp_{int(time.time())}"
                        task.workdir = os.path.join(self.args.output_dir, folder_name)

                os.makedirs(task.workdir, exist_ok=True)

                # DISCOVERY: Warp to furthest stage if files exist
                found_stage = self.discover_stage(task.workdir)
                if found_stage == "DONE":
                    task.set_status("DONE")
                    for s in ["DL", "TR", "TL", "MR", "BR"]: task.pcts[s] = 100.0
                    self.queues["DL"].task_done()
                    continue
                elif found_stage != "DL":
                    self.log(f"Stage {found_stage} output already exists for task {task.uid}, warping ahead...")
                    stages = ["DL", "TR", "TL", "MR", "BR"]
                    idx = stages.index(found_stage)
                    for i in range(idx): task.pcts[stages[i]] = 100.0
                    self.queues[found_stage].put(task)
                    self.queues["DL"].task_done()
                    continue

                # Regular download
                cmd = list(VDOWN_CMD) + [task.url, self.args.cookies or "", task.workdir]
                if self.args.proxy: cmd.extend(["--proxy", self.args.proxy])

                if self.run_cmd(task, cmd, "DL"):
                    self.queues["TR"].put(task)

                self.queues["DL"].task_done()
            except queue.Empty:
                continue
            except Exception as e:
                self.log(f"Error in DL Worker [{type(e).__name__}]: {e}")
                if 'task' in locals() and task:
                    self.queues["DL"].task_done()
                time.sleep(1)

    def tr_worker(self):
        self.log("Worker thread [TR] started")
        while not self.global_abort:
            self.global_pause.wait()
            task = None
            try:
                task = self.queues["TR"].get(timeout=1)
                self.log(f"TR Worker picked up Task {task.uid}")
                if task.status == "FAILED" or task.is_manual_paused:
                    self.queues["TR"].task_done()
                    continue

                if not task.workdir or not os.path.exists(task.workdir):
                    task.error = "TR FAILED: Workspace directory missing"
                    task.set_status("FAILED")
                    self.queues["TR"].task_done()
                    continue

                # Check if TR output already exists
                existing_srt = self.find_local_file(task.workdir, ['.srt'], exclude_pattern=r'(\.zh|\.cn|\.bi)\.srt$')
                if existing_srt:
                    self.log(f"Transcript exists for task {task.uid}: {os.path.basename(existing_srt)}, skipping TR.")
                    task.update_pct("TR", 100.0)
                    self.queues["TL"].put(task)
                    self.queues["TR"].task_done()
                    continue

                # Find the local video file in workdir
                local_video = self.find_local_file(task.workdir, ['.mp4', '.mkv', '.webm'])
                if not local_video:
                    task.error = f"TR FAILED: No video file found in {task.workdir}"
                    task.set_status("FAILED")
                    self.queues["TR"].task_done()
                    continue

                cmd = list(TRANSCRIBER_CMD) + [local_video, "--model", self.args.model, "--output", task.workdir, "--no-gui"]
                if self.run_cmd(task, cmd, "TR"):
                    self.queues["TL"].put(task)

                self.queues["TR"].task_done()
            except queue.Empty:
                continue
            except Exception as e:
                self.log(f"Error in TR Worker [{type(e).__name__}]: {e}")
                if 'task' in locals() and task:
                    self.queues["TR"].task_done()
                time.sleep(1)

    def tl_worker(self):
        self.log("Worker thread [TL] started")
        while not self.global_abort:
            self.global_pause.wait()
            task = None
            try:
                task = self.queues["TL"].get(timeout=1)
                self.log(f"TL Worker picked up Task {task.uid}")

                if not task.workdir or not os.path.exists(task.workdir):
                    task.error = "TL FAILED: Workspace directory missing"
                    task.set_status("FAILED")
                    self.queues["TL"].task_done()
                    continue

                # Check if TL output already exists
                existing_zh = self.find_local_file(task.workdir, ['.srt'], pattern=r'(\.zh|\.cn)\.srt$')
                if existing_zh:
                    self.log(f"Translation exists for task {task.uid}: {os.path.basename(existing_zh)}, skipping TL.")
                    task.update_pct("TL", 100.0)
                    self.queues["MR"].put(task)
                    self.queues["TL"].task_done()
                    continue

                # Find the local English SRT (usually .srt or .en.srt)
                local_srt = self.find_local_file(task.workdir, ['.srt'], exclude_pattern=r'(\.zh|\.cn|\.bi)\.srt$')
                if not local_srt:
                    task.error = f"TL FAILED: No source SRT found in {task.workdir}"
                    task.set_status("FAILED")
                    self.queues["TL"].task_done()
                    continue

                # TL: subtranslator.py translate <en_srt>
                cmd = list(SUBTRANSLATOR_CMD) + ["translate", local_srt]

                # Global API protection enforced here
                if self.run_cmd(task, cmd, "TL", is_api_heavy=True):
                    self.queues["MR"].put(task)

                self.queues["TL"].task_done()
            except queue.Empty:
                continue
            except Exception as e:
                self.log(f"Error in TL Worker [{type(e).__name__}]: {e}")
                if 'task' in locals() and task:
                    self.queues["TL"].task_done()
                time.sleep(1)

    def mr_worker(self):
        self.log("Worker thread [MR] started")
        while not self.global_abort:
            self.global_pause.wait()
            task = None
            try:
                task = self.queues["MR"].get(timeout=1)
                self.log(f"MR Worker picked up Task {task.uid}")

                if not task.workdir or not os.path.exists(task.workdir):
                    task.error = "MR FAILED: Workspace directory missing"
                    task.set_status("FAILED")
                    self.queues["MR"].task_done()
                    continue

                # Check if MR output already exists
                existing_bi = self.find_local_file(task.workdir, ['.srt'], pattern=r'\.bi\.srt$')
                if existing_bi:
                    self.log(f"Bilingual SRT exists for task {task.uid}: {os.path.basename(existing_bi)}, skipping MR.")
                    task.update_pct("MR", 100.0)
                    self.queues["BR"].put(task)
                    self.queues["MR"].task_done()
                    continue

                # Find local EN and ZH SRTs
                en_srt = self.find_local_file(task.workdir, ['.srt'], exclude_pattern=r'(\.zh|\.cn|\.bi)\.srt$')
                zh_srt = self.find_local_file(task.workdir, ['.srt'], pattern=r'(\.zh|\.cn)\.srt$')

                if not en_srt or not zh_srt:
                    task.error = "MR FAILED: Missing EN or ZH SRT for merge"
                    task.set_status("FAILED")
                    self.queues["MR"].task_done()
                    continue

                # MR: subtranslator.py merge <en_srt> --translated-file <zh_srt>
                cmd = list(SUBTRANSLATOR_CMD) + ["merge", en_srt, "--translated-file", zh_srt]

                if self.run_cmd(task, cmd, "MR"):
                    self.queues["BR"].put(task)

                self.queues["MR"].task_done()
            except queue.Empty:
                continue
            except Exception as e:
                self.log(f"Error in MR Worker [{type(e).__name__}]: {e}")
                if 'task' in locals() and task:
                    self.queues["MR"].task_done()
                time.sleep(1)

    def br_worker(self):
        self.log("Worker thread [BR] started")
        while not self.global_abort:
            self.global_pause.wait()
            task = None
            try:
                task = self.queues["BR"].get(timeout=1)
                self.log(f"BR Worker picked up Task {task.uid}")

                if not task.workdir or not os.path.exists(task.workdir):
                    task.error = "BR FAILED: Workspace directory missing"
                    task.set_status("FAILED")
                    self.queues["BR"].task_done()
                    continue

                # Check if BR output already exists
                existing_hardsub = self.find_local_file(task.workdir, ['.mp4', '.mkv'], pattern=r'_hardsub')
                if existing_hardsub:
                    self.log(f"Hardsubbed video exists for task {task.uid}, skipping BR.")
                    task.update_pct("BR", 100.0)
                    task.set_status("DONE")
                    self.queues["BR"].task_done()
                    continue

                # Logic: Build CMD for srt_to_ass -> burn_engine
                best_srt = self.find_local_file(task.workdir, ['.srt'], pattern=r'\.bi\.srt$')
                if not best_srt:
                    best_srt = self.find_local_file(task.workdir, ['.srt'], pattern=r'(\.zh|\.cn)\.srt$')

                local_video = self.find_local_file(task.workdir, ['.mp4', '.mkv', '.webm'], exclude_pattern=r'_hardsub')

                if not best_srt or not local_video:
                    task.error = "BR FAILED: Missing SRT or Video for burning"
                    task.set_status("FAILED")
                    self.queues["BR"].task_done()
                    continue

                video_path = local_video
                srt_path = best_srt
                ass_path = os.path.splitext(srt_path)[0] + ".ass"
                out_vid = os.path.splitext(video_path)[0] + "_hardsub" + os.path.splitext(video_path)[1]

                # Step 1: SRT to ASS
                w, h = self.get_video_dimensions(video_path)
                ass_cmd = list(SRT2ASS_CMD) + [srt_path, ass_path, "--layout", "bilingual", "--width", str(w), "--height", str(h)]
                self.log(f"   [BR] Generating ASS for Task {task.uid}...")
                if self.run_cmd(task, ass_cmd, "BR_ASS"):
                    # Step 2: Burn ASS
                    burn_cmd = list(BURNSUB_CMD) + [video_path, ass_path, out_vid, "--headless"]
                    self.log(f"   [BR] Burning Video for Task {task.uid}...")
                    if self.run_cmd(task, burn_cmd, "BR_BURN"):
                        task.set_status("DONE")

                self.queues["BR"].task_done()
            except queue.Empty:
                continue
            except Exception as e:
                self.log(f"Error in BR Worker [{type(e).__name__}]: {e}")
                if 'task' in locals() and task:
                    self.queues["BR"].task_done()
                time.sleep(1)


# --- Dashboard TUI ---
class Dashboard:
    def __init__(self, mgr: PipelineManager):
        self.mgr = mgr
        self.console = Console()
        self.scroll_idx = 0
        self.page_size = 10
        self.cmd_buffer = ""

    def generate_table(self):
        console_w = self.console.size.width
        console_h = self.console.size.height
        third = max(20, console_w // 3)

        # Self-healing: Reset scroll if beyond bounds
        if self.scroll_idx >= len(self.mgr.task_map) and self.scroll_idx > 0:
            self.scroll_idx = 0

        with self.mgr.lock:
            tasks_list = list(self.mgr.task_map.values())
            tasks_list.sort(key=lambda x: x.uid)
            visible_tasks = tasks_list[self.scroll_idx : self.scroll_idx + self.page_size]

            # Use fixed column layout for better stability on resize
            max_title_len = max([len(t.display_title) for t in visible_tasks]) if visible_tasks else 30

            table = Table(box=box.ROUNDED, border_style="grey30", header_style="bold cyan", expand=True, padding=(0, 1))
            table.add_column("UID", width=4, justify="center")
            table.add_column("视频标题", ratio=3, overflow="ellipsis")
            table.add_column("总进度 (DL -> TR -> TL -> MR -> BR)", ratio=4, justify="center")
            for s in ["下载", "转录", "翻译", "合并", "压制"]:
                table.add_column(s, width=7, justify="right")

            if not visible_tasks:
                table.add_row("-", "[dim]无任务[/dim]", "[dim]等待状态加载...[/dim]", "", "", "", "", "")

            for t in visible_tasks:
                is_p = getattr(t, 'is_manual_paused', False)
                is_f = "FAILED" in t.status

                # Dynamic Bar Width Calculation
                # Get the actual width assigned by Rich if possible? No, we use weighted segments.
                # Since 'ratio=1' bar might be anything from 20 to 60 chars.
                # Let's estimate bar characters based on terminal context
                # If Rule 1: about 'third' chars. If Rule 2: 1/2 of terminal.
                est_bar_chars = third if max_title_len > third else (console_w - max_title_len - 45)
                est_bar_chars = max(10, min(100, est_bar_chars - 10)) # safety

                # Weighted allocation: sum should match est_bar_chars
                segments = [("DL", 0.05), ("TR", 0.45), ("TL", 0.20), ("MR", 0.05), ("BR", 0.25)]
                bar_parts = []
                for s, weight in segments:
                    width = max(1, int(weight * est_bar_chars))
                    p = (t.get_br_pct() if s == "BR" else t.pcts.get(s)) or 0.0
                    filled = int(p / 100 * width)

                    if p >= 100.0:
                        # Only show green if the stage is NOT active or waiting?
                        # Actually, if p is 100, it's done for that stage.
                        bar_parts.append(f"[green]{'▄' * width}[/green]")
                    elif p > 0 or t.is_active(s) or f"WAIT ({s})" in t.status:
                        # ACTIVE or WAIT
                        is_w = f"WAIT ({s})" in t.status
                        color = "red" if is_f else "yellow" if (is_p or is_w) else "bright_blue"
                        bar_parts.append(f"[{color}]{'▄' * filled}[/{color}][grey30]{'▄' * (width - filled)}[/grey30]")
                    else:
                        bar_parts.append(f"[grey30]{'▄' * width}[/grey30]")

                bar_display = "".join(bar_parts)

                pct_cols = []
                for s in ["DL", "TR", "TL", "MR", "BR"]:
                    p = (t.get_br_pct() if s == "BR" else t.pcts.get(s)) or 0.0

                    # Status determination for this cell
                    is_w = f"WAIT ({s})" in t.status
                    is_a = t.is_active(s)

                    color = "grey30"
                    if p >= 100.0: color = "green"
                    elif is_f and (is_a or is_w): color = "red"
                    elif is_w: color = "yellow"
                    elif is_a: color = "bright_blue"
                    elif is_p and (is_a or is_w): color = "yellow"

                    # Exception: Burning (BR) shouldn't be green 100% if it's not DONE
                    if s == "BR" and p >= 100.0 and t.status != "DONE":
                        color = "bright_blue" # Still working on it (e.g. merging final parts)

                    pct_cols.append(f"[{color}]{int(p)}%[/{color}]")

                table.add_row(str(t.uid), t.display_title, bar_display, *pct_cols)
        return table

    def generate_layout(self):
        # Dynamic row adaptation based on terminal height
        term_h = self.console.size.height
        # Header(3) + Footer(5) + Table Chrome(4) = 12 lines overhead.
        # Ensure a minimum of 5 visible tasks.
        new_page_size = max(5, term_h - 12)
        if new_page_size != self.page_size:
            self.page_size = new_page_size
            # Adjust scroll index to keep it within safe bounds after resize
            max_scroll = max(0, len(self.mgr.task_map) - self.page_size)
            self.scroll_idx = min(self.scroll_idx, max_scroll)

        # Self-healing for empty visible list
        if self.scroll_idx > 0 and self.scroll_idx >= len(self.mgr.task_map):
            self.scroll_idx = 0

        layout = Layout()
        layout.split(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=4) # Reduce to 4 to prevent overflow/flickering
        )
        layout["header"].update(Panel(Align.center("[bold cyan]AutoSub Pro 批量视频字幕处理系统[/bold cyan]"), box=box.SIMPLE))
        layout["body"].update(self.generate_table())

        cmd_info = getattr(self, 'cmd_buffer', "")
        help_msg = "P: 暂停/继续 | S+ID挂起 | R+ID重启 | O退出界面 | Q终止 | ↑/↓滚动"

        # Metric Snapshot
        total_count = len(self.mgr.task_map)
        active_count = len(self.mgr.active_uids)
        q_info = " | ".join([f"{k}:{self.mgr.queues[k].qsize()}" for k in self.mgr.queues])
        metric_line = f"活跃任务: {active_count} | 队列: {q_info} | 总任务: {total_count}"

        if self.mgr.is_watcher:
            help_msg = "[bold green]WATCHER[/bold green] | " + help_msg

        if cmd_info:
            help_msg = f"[bold yellow]{cmd_info}[/bold yellow] | " + help_msg

        # Consistent layout padding to avoid flickering
        layout["footer"].update(Panel(f"{metric_line}\n{help_msg}", title="[bold white]SYS CONSOLE[/bold white]", box=box.ROUNDED, border_style="blue"))
        return layout

    def run(self):
        last_save = 0
        last_heartbeat = 0
        if getattr(self.mgr.args, 'daemon', False):
            # Headless Daemon Loop
            self.mgr.log("AutoSub Daemon Started (Headless Mode)")
            while not self.mgr.global_abort:
                try:
                    if time.time() - last_save > 5:
                        self.mgr.save_state()
                        self.mgr.handle_external_commands()
                        last_save = time.time()

                    if time.time() - last_heartbeat > 30:
                        active_count = len(self.mgr.active_uids)
                        self.mgr.log(f"HEARTBEAT: Health Check OK. Active Tasks: {active_count}. Slots: {self.mgr.task_limit}")
                        last_heartbeat = time.time()

                    time.sleep(1.0)
                except Exception as e:
                    self.mgr.log(f"CRITICAL ERROR in Daemon Loop: {e}")
                    time.sleep(5)
            self.mgr.log("AutoSub Daemon Shutting Down")
            return

        with Live(self.generate_layout(), refresh_per_second=1, screen=True) as live:
            while not self.mgr.global_abort:
                live.update(self.generate_layout())
                if time.time() - last_save > 5:
                    if self.mgr.is_watcher:
                        self.mgr.load_state()
                    else:
                        self.mgr.save_state()
                        self.mgr.handle_external_commands()
                    last_save = time.time()
                time.sleep(1)

# --- CLI Handling ---
def key_listener(mgr, dash):
    if sys.platform == "win32":
        import msvcrt
    else:
        import select
        import termios
        import tty

        def _getch():
            fd = sys.stdin.fileno()
            if not os.isatty(fd): return None
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(sys.stdin.fileno())
                ch = sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            return ch.encode('utf-8')

        def _kbhit():
            if not os.isatty(sys.stdin.fileno()): return False
            return select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], [])

        class _msvcrt_mock:
            @staticmethod
            def kbhit(): return _kbhit()
            @staticmethod
            def getch(): return _getch()
        msvcrt = _msvcrt_mock()
    cmd_mode = None # Can be 'S' or 'R'
    id_buffer = ""

    while not mgr.global_abort:
        if msvcrt.kbhit():
            ch_raw = msvcrt.getch()

            # 1. Handle Windows Special Keys (Arrows)
            if ch_raw in [b'\x00', b'\xe0']:
                ch_next = msvcrt.getch()
                scancode = ord(ch_next) if ch_next else 0
                if scancode == 72: # Up Arrow
                    dash.scroll_idx = max(0, dash.scroll_idx - 1)
                elif scancode == 80: # Down Arrow
                    max_scroll = max(0, len(mgr.task_map) - dash.page_size)
                    dash.scroll_idx = min(max_scroll, dash.scroll_idx + 1)
                continue

            # 2. Decode character
            ch_byte = ""
            if ch_raw:
                try: ch_byte = ch_raw.decode('utf-8')
                except: ch_byte = ""
            ch_lower = ch_byte.lower()

            # 3. State-Machine Logic: If NOT in Command Mode
            if not cmd_mode:
                if ch_lower == 'q':
                    if mgr.is_watcher: mgr.send_cmd(None, "terminate")
                    mgr.global_abort = True
                elif ch_lower == 'p':
                    if mgr.global_pause.is_set():
                        mgr.global_pause.clear()
                        if mgr.is_watcher:
                            mgr.send_cmd(None, "pause_all")
                        else:
                            # Suspend all active tasks
                            with mgr.lock:
                                for uid in list(mgr.active_uids):
                                    t = mgr.task_map.get(uid)
                                    if t and t.pid: ProcessTree.suspend(t.pid)
                    else:
                        mgr.global_pause.set()
                        if mgr.is_watcher:
                            mgr.send_cmd(None, "resume_all")
                        else:
                            # Resume all active tasks
                            with mgr.lock:
                                for uid in list(mgr.active_uids):
                                    t = mgr.task_map.get(uid)
                                    if t and t.pid: ProcessTree.resume(t.pid)
                elif ch_lower == 'o':
                    mgr.global_abort = True
                elif ch_lower == 's':
                    cmd_mode = 'S'
                    dash.cmd_buffer = "PAUSE Task ID: "
                elif ch_lower == 'r':
                    cmd_mode = 'R'
                    dash.cmd_buffer = "RESTART Task ID: "

            # 4. State-Machine Logic: If IN Command Mode (Waiting for Digits)
            else:
                if ch_byte.isdigit():
                    id_buffer += ch_byte
                    dash.cmd_buffer += ch_byte
                elif ch_raw == b'\x08': # Backspace
                    if id_buffer:
                        id_buffer = id_buffer[:-1]
                        dash.cmd_buffer = dash.cmd_buffer[:-1]
                elif ch_raw == b'\x1b': # Escape
                    cmd_mode = None
                    id_buffer = ""
                    dash.cmd_buffer = ""
                elif ch_byte == '\r': # Enter
                    if id_buffer:
                        uid = int(id_buffer)
                        if mgr.is_watcher: mgr.send_cmd(uid, "pause" if cmd_mode == 'S' else "restart")
                        else:
                            if cmd_mode == 'S': mgr.toggle_task_pause(uid)
                            elif cmd_mode == 'R': mgr.restart_task(uid)
                    cmd_mode = None
                    id_buffer = ""
                    dash.cmd_buffer = ""

        time.sleep(0.05)

def confirm_cookies(args):
    """Proactive cookie check with fallback discovery."""
    if getattr(args, 'cookies', None):
        return args.cookies

    search_paths = []

    # Priority defaults
    search_paths = [
        r"D:\download\cookies.txt",
        r"D:\Downloads\cookies.txt",
        r"/Users/shanfu/cc/cookies.txt",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt"),
    ]

    found_path = None
    for p in search_paths:
        if os.path.exists(p):
            found_path = p
            break

    if not found_path:
        if not args.daemon and sys.stdin.isatty():
            input(f"\n[bold yellow]请在此终端按回车键继续...[/bold yellow]")
        print("\n[bold yellow]⚠️  警告: 未找到 Cookie 文件。[/bold yellow]")
        print("   如果处理 YouTube 视频，可能会遇到机器人检测错误。")
        if not args.silent:
            print("   建议提供 --cookies 参数或将 cookies.txt 放入 D:\\download\\")
            print("   任务将在 3 秒后尝试继续...")
            time.sleep(3)
        return None

    def validate_cookies(path):
        with open(path, 'r', errors='ignore') as f:
            content = f.read(1024)
            if "Netscape" in content or "youtube.com" in content:
                return True, "有效的 Netscape 格式"
            return False, "不兼容的格式"

    is_valid, reason = validate_cookies(found_path)
    mtime = datetime.fromtimestamp(os.path.getmtime(found_path)).strftime('%Y-%m-%d %H:%M:%S')
    size_kb = os.path.getsize(found_path) / 1024

    print(f"\n[bold green]🍪 检测到 Cookie 文件:[/bold green]")
    print(f"   路径: [cyan]{found_path}[/cyan]")
    print(f"   时间: [white]{mtime}[/white]")
    print(f"   大小: [white]{size_kb:.1f} KB[/white]")
    print(f"   检查: [white]{reason}[/white]")

    if args.silent or args.daemon:
        args.cookies = found_path
        return found_path

    if not args.daemon and not args.silent and sys.stdin.isatty():
        input(f"\n[bold yellow]请在此终端按回车键继续...[/bold yellow]")
    args.cookies = found_path
    return found_path

def real_main():
    parser = argparse.ArgumentParser(description="AutoSub Batch Pro v3")
    parser.add_argument("--batch-urls", nargs="+", help="Multiple YouTube URLs")
    parser.add_argument("--batch-file", help="File containing list of URLs")
    parser.add_argument("--output-dir", default=DOWNLOAD_ROOT, help="Base output directory")
    parser.add_argument("--max-tasks", type=int, default=4, help="Global concurrency limit")
    parser.add_argument("--max-api-calls", type=int, default=20, help="LLM API concurrency limit")
    parser.add_argument("--workers", type=int, default=5, help="Worker threads per stage")
    parser.add_argument("--model", default="large-v2", help="Whisper model size")
    parser.add_argument("--llm-model", default="gemini-3-pro-preview", help="LLM Model (gemini-3-flash-preview, gemini-3-pro-preview, gpt-4o, etc.)")
    parser.add_argument("--cookies", help="Path to cookies.txt")
    parser.add_argument("--proxy", help="Proxy URL")
    parser.add_argument("--status", action="store_true", help="Watcher mode: view dashboard without starting master")
    parser.add_argument("--silent", action="store_true", help="Start master in headless background mode")
    parser.add_argument("--daemon", action="store_true", help="INTERNAL: used by daemonized process")
    parser.add_argument("--dashboard", action="store_true", help="Dashboard: Open watcher in a new window")
    parser.add_argument("--state-file", help="Override state file path")

    args = parser.parse_args()

    # Independent Dashboard Window Launcher
    if args.dashboard:
        target_sf = args.state_file
        if not target_sf:
            cwd_state = os.path.join(os.getcwd(), "autosub_batch_state.json")
            if os.path.exists(cwd_state):
                target_sf = cwd_state
            else:
                # Search Projects dir
                projects_root = os.path.join(os.getcwd(), "Projects")
                if os.path.exists(projects_root):
                    project_folders = [f for f in os.listdir(projects_root) if os.path.isdir(os.path.join(projects_root, f))]
                    for pf in project_folders:
                        sf_cand = os.path.join(projects_root, pf, "autosub_batch_state.json")
                        if os.path.exists(sf_cand):
                            target_sf = sf_cand
                            break

        cmd_args = ["--status"]
        if target_sf: cmd_args += ["--state-file", f'"{target_sf}"']

        if sys.platform == "win32":
            # Using 'start' is the most reliable way on Windows to spawn a new window.
            # The first quoted argument to 'start' is the window title.
            title = f"AutoSub_Dashboard_{os.path.basename(target_sf) if target_sf else 'New'}"
            launch_cmd = f'start "{title}" "{sys.executable}" "{os.path.abspath(__file__)}" --status'
            if target_sf:
                launch_cmd += f' --state-file "{target_sf}"'

            subprocess.Popen(launch_cmd, shell=True)
            print(f"🚀 已在独立窗口启动监控仪表盘。")
            sys.exit(0)

    if not args.state_file or not os.path.exists(args.state_file):
        # Fallback 1: check current directory
        cwd_state = os.path.join(os.getcwd(), "autosub_batch_state.json")
        if os.path.exists(cwd_state):
            args.state_file = cwd_state
        elif args.status:
            # Fallback 2: For status mode, look in Projects subfolders
            projects_root = os.path.join(os.getcwd(), "Projects")
            if os.path.exists(projects_root):
                for d in os.listdir(projects_root):
                    cand = os.path.join(projects_root, d, "autosub_batch_state.json")
                    if os.path.exists(cand):
                        args.state_file = cand
                        break

        if not args.state_file:
            args.state_file = os.path.join(args.output_dir, "autosub_batch_state.json")

    has_state = os.path.exists(args.state_file)
    if not args.batch_urls and not args.batch_file and not args.status and not args.daemon and not has_state:
        print("💡 Hint: No new URLs provided. Please provide --batch-urls, --batch-file, or --output-dir with an existing project.")
        return

    # Check status of cookies before starting anything worker-heavy
    if not args.status:
        confirm_cookies(args)

    # Enforce global worker limit
    max_workers = min(args.workers, 10)

    mgr = PipelineManager(args)
    mgr.silent_mode = args.silent

    # Always try to load existing state to resume progress
    if os.path.exists(mgr.state_path):
        mgr.load_state()

    # Initialize Dashboard for TUI
    dash = Dashboard(mgr)

    # 0. Watcher mode (attach to existing state)
    if args.status:
        threading.Thread(target=key_listener, args=(mgr, dash), daemon=True).start()
        dash.run()
        return

    # 1. Expand Inputs into URLs (Bypass in daemon if already loaded)
    if args.daemon and len(mgr.task_map) > 0:
        mgr.log(f"Fast Startup: Resuming {len(mgr.task_map)} tasks from state file.")
    else:
        target_urls = []
        if args.batch_urls: target_urls.extend(args.batch_urls)
        if args.batch_file and os.path.exists(args.batch_file):
            with open(args.batch_file, "r", encoding='utf-8-sig') as f:
                target_urls.extend([l.strip() for l in f if l.strip() and not l.startswith("#")])

        if target_urls:
            print(f"Processing {len(target_urls)} inputs...")
            for url_input in target_urls:
                mgr.add_task(url_input)

    # 2. Master Detachment (After targets resolved)
    # [REFINED] Default behavior: If not status/daemon, spawn a new window for the master
    # and turn the current process into a status watcher.
    if not args.status and not args.daemon:
        mgr.save_state()
        mgr.log(f"[SYSTEM] Launching Master in a separate window (Explicit Mode)...")

        # On Windows, start a new visible terminal window
        if sys.platform == "win32":
            # Pass all arguments but add --daemon to the child
            cmd_args = ["--daemon"] + sys.argv[1:]
            # Ensure paths are quoted for PowerShell
            ps_cmd = f'Start-Process powershell -ArgumentList "-NoExit", "-Command", "{sys.executable} \\"{os.path.abspath(__file__)}\\" {" ".join(cmd_args)}"'
            subprocess.Popen(["powershell", "-Command", ps_cmd])
        elif sys.platform == "darwin":
            cmd_args = ["--daemon"] + sys.argv[1:]
            mac_cmd = f"'{sys.executable}' '{os.path.abspath(__file__)}' {' '.join(cmd_args)}"
            osascript_cmd = f'tell application "Terminal" to do script "{mac_cmd}"'
            subprocess.Popen(["osascript", "-e", osascript_cmd])
        else:
            cmd = [sys.executable, __file__, "--daemon"] + sys.argv[1:]
            subprocess.Popen(cmd)

        # Current process becomes a STATUS WATCHER
        args.status = True
        mgr.is_watcher = True
        dash.mgr = mgr # Refresh link

    # 3. Launch Workers (only in master mode)
    if not args.status:
        for _ in range(max_workers):
            threading.Thread(target=mgr.dl_worker, daemon=True).start()
            threading.Thread(target=mgr.tr_worker, daemon=True).start()
            threading.Thread(target=mgr.tl_worker, daemon=True).start()
            threading.Thread(target=mgr.mr_worker, daemon=True).start()
            threading.Thread(target=mgr.br_worker, daemon=True).start()

    # Always enable keyboard listener if we are running the TUI (unless silent background or daemon)
    if not args.silent and not args.daemon:
        threading.Thread(target=key_listener, args=(mgr, dash), daemon=True).start()

    # 4. START TUI (Master with UI or Watcher)
    if not args.daemon:
        dash.run()
    else:
        # Background Master Loop: Just wait for exit or shutdown
        mgr.log("[SYSTEM] Daemonized Master running in background loop...")
        try:
            while not mgr.global_abort:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    # 5. Cleanup
    mgr.shutdown()

def main():
    try:
        real_main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n[CRITICAL ERROR] {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()