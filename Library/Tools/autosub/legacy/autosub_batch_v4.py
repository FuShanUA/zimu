import os
import sys
import subprocess
import time
import json
import re
import threading
import queue
import argparse
import shutil
import glob
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field, asdict
from contextlib import contextmanager
import tempfile

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

# UI & Tools
import logging
import psutil
if sys.platform == "win32":
    import msvcrt
else:
    import select
    import termios
    import tty

    def _getch():
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return None
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch.encode('utf-8')

    def _kbhit():
        if not os.isatty(sys.stdin.fileno()):
            return False
        return select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], [])

    class _msvcrt_mock:
        @staticmethod
        def kbhit(): return _kbhit()
        @staticmethod
        def getch(): return _getch()
    
    msvcrt = _msvcrt_mock()
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.align import Align
from rich.text import Text
from rich import box

# --- Configuration & Paths ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.dirname(CURRENT_DIR)
# Default output to a 'Projects' folder inside the root
# Heuristic: Find 'Projects' folder relative to script or go up from Library/Tools/autosub
_p = CURRENT_DIR
for _ in range(3): _p = os.path.dirname(_p)
PROJECT_ROOT = _p if os.path.basename(_p).lower() != "library" else os.path.dirname(_p)
DEFAULT_OUTPUT_ROOT = os.path.join(PROJECT_ROOT, "Projects")
LOG_DIR = os.path.join(DEFAULT_OUTPUT_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Global Logging Setup
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "autosub_batch_v4.log"),
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s',
    encoding='utf-8'
)
logger = logging.getLogger("AutoSubBatch")

# --- Robust Tool Discovery ---
def get_ytdlp_path():
    # 1. Check local tools folder
    local_ytdlp = os.path.join(TOOLS_DIR, "vdown", "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp")
    if os.path.exists(local_ytdlp): return local_ytdlp
    # 2. Check PATH
    path = shutil.which("yt-dlp")
    if path: return path
    # 3. Fallback to venv if available
    venv_ytdlp = os.path.join(CURRENT_DIR, ".venv", "bin", "yt-dlp")
    if os.path.exists(venv_ytdlp): return venv_ytdlp
    return "yt-dlp"

YTDLP_EXE = get_ytdlp_path()

# --- Robust Tool Discovery ---
def get_tool_path(tool_name="ffmpeg"):
    """Heuristic search for system binaries on Windows."""
    path = shutil.which(tool_name)
    if path: return path

    # Check WinGet Gyan Tool Location
    user_home = os.path.expanduser("~")
    winget_base = os.path.join(user_home, "AppData", "Local", "Microsoft", "Winget", "Packages")
    if os.path.exists(winget_base):
        for d in os.listdir(winget_base):
            if tool_name in d:
                for bin_dir in glob.glob(os.path.join(winget_base, d, "**/bin"), recursive=True):
                    tool_path = os.path.join(bin_dir, f"{tool_name}.exe")
                    if os.path.exists(tool_path): return tool_path

    fallbacks = [
        r"C:\ffmpeg\bin",
        r"C:\Program Files\ffmpeg\bin",
        r"D:\Program Files\CapCut\7.7.0.3143", # User-specific for CapCut's FFmpeg
    ]
    for fb in fallbacks:
        p = os.path.join(fb, f"{tool_name}.exe")
        if os.path.exists(p): return p
    return tool_name

FFMPEG_EXE = get_tool_path("ffmpeg")
FFPROBE_EXE = get_tool_path("ffprobe")

# --- Cookie Management ---
@contextmanager
def use_temp_cookies(cookies_path):
    """Creates a temporary isolated copy of the cookies file."""
    if not cookies_path or not os.path.exists(cookies_path):
        yield None
        return

    fd, temp_path = tempfile.mkstemp(suffix=".txt", prefix="cookies_")
    os.close(fd)

    try:
        shutil.copy2(cookies_path, temp_path)
        yield temp_path
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except: pass

# --- Process Management ---
class ProcessTree:
    """Manages cross-platform process suspension and termination."""
    @staticmethod
    def kill(pid):
        if not pid: return
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children: child.kill()
            parent.kill()
        except: pass

    @staticmethod
    def suspend(pid):
        if not pid: return
        try:
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True): child.suspend()
            parent.suspend()
        except: pass

    @staticmethod
    def resume(pid):
        if not pid: return
        try:
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True): child.resume()
            parent.resume()
        except: pass

# --- Data Models ---
@dataclass
class SubTask:
    uid: int
    url: str
    title: str = "加载中..."
    status: str = "排队中" # QUEUED, ACTIVE (STAGE), DONE, FAILED, PAUSED
    pcts: Dict[str, float] = field(default_factory=lambda: {"DL": 0.0, "TR": 0.0, "TL": 0.0, "MR": 0.0, "BR": 0.0, "GD": 0.0})
    workdir: Optional[str] = None
    error: Optional[str] = None
    pid: Optional[int] = None
    is_paused: bool = False
    retries: int = 0
    queued_stages: set = field(default_factory=set) # Set of stages this task is currently in (DL, TR, etc.)
    sub_dir: Optional[str] = None # Optional sub-directory within output_root


    def to_dict(self):
        d = asdict(self)
        d['pid'] = None # Don't persist PIDs
        # Do NOT persist queued_stages to avoid persistence deadlocks on restart
        d['queued_stages'] = []
        return d

    @classmethod
    def from_dict(cls, d):
        # Handle cases where keys might be missing in older states
        return cls(
            uid=d['uid'],
            url=d['url'],
            title=d.get('title', 'Unknown'),
            status=d.get('status', 'QUEUED'),
            pcts=d.get('pcts', {"DL": 0.0, "TR": 0.0, "TL": 0.0, "MR": 0.0, "BR": 0.0, "GD": 0.0}),
            workdir=d.get('workdir'),
            error=d.get('error'),
            is_paused=d.get('is_paused', False),
            retries=d.get('retries', 0),
            queued_stages=set(d.get('queued_stages', [])),
            sub_dir=d.get('sub_dir')
        )

# --- Hardware & Resource Orchestrator ---
class HardwareManager:
    """Manages machine-specific hardware detection and persistence."""
    def __init__(self, config_dir: str):
        import socket
        self.hostname = socket.gethostname()
        # Store in the tool dir, but uniquely named by hostname to avoid sync-carryover
        self.config_path = os.path.join(config_dir, f".hw_{self.hostname}.json")
        self.config = self._load_or_detect()

    def _load_or_detect(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass

        # Detect Hardware
        import multiprocessing
        cpu_count = multiprocessing.cpu_count()
        has_cuda = False
        if sys.platform == "win32":
            try:
                import ctypes
                # Safe access to windll for linters on Mac
                windll = getattr(ctypes, 'windll', None)
                if windll:
                    has_cuda = bool(windll.kernel32.GetModuleHandleW("nvcuda.dll"))
            except: pass
        else:
            # On Mac/Linux, we might check for nvidia-smi or use torch/tensorflow discovery
            # For now, let's assume False unless we want to add more complex discovery
            pass

        # Determine Concurrency Profile
        # TR and BR are now separated to avoid stage starvation
        tr_max = 1
        br_max = 1
        is_mac = sys.platform == "darwin"
        
        if has_cuda or is_mac:
            # If we have a dedicated GPU or high-performance Mac Silicon
            tr_max = 2
            br_max = 2
            
            # Optimization for high-end Macs
            if is_mac and cpu_count > 8:
                tr_max = 3
                br_max = 3

        config = {
            "hostname": self.hostname,
            "cpu_count": cpu_count,
            "has_cuda": has_cuda,
            "heavy_max": tr_max + br_max, # Keep for backward compatibility
            "tr_max": tr_max,
            "br_max": br_max,
            "api_pro_max": 20,
            "api_flash_max": 100,
            "io_max": 6
        }

        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            logger.info(f"Hardware profile generated and saved for {self.hostname}")
        except Exception as e:
            logger.error(f"Failed to save hardware profile: {e}")

        return config

    def get(self, key, default=None):
        return self.config.get(key, default)

# --- Concurrency & Resource Orchestrator ---
class ResourceManager:
    """Manages task scheduling and concurrency limits for different resources."""
    def __init__(self, config_dir: str):
        self.hw = HardwareManager(config_dir)

        # Split-Rail Concurrency: Independent semaphores for TR and BR
        # Fallback to half of heavy_max if tr_max/br_max are missing in older configs
        h_max = self.hw.get("heavy_max", 2)
        default_split = max(1, h_max // 2)

        self.tr_sem = threading.Semaphore(self.hw.get("tr_max", default_split))
        self.br_sem = threading.Semaphore(self.hw.get("br_max", default_split))

        self.api_sem = threading.Semaphore(self.hw.get("api_pro_max", 20))     # 3.1-pro models
        self.tl_flash_sem = threading.Semaphore(self.hw.get("api_flash_max", 100)) # Flash models
        self.io_sem = threading.Semaphore(self.hw.get("io_max", 6))       # Download
        self.mr_sem = threading.Semaphore(20)                            # Merge (Lightweight)
        self.gd_sem = threading.Semaphore(1)                             # Sequential sync to prevent race conditions
        self.meta_sem = threading.Semaphore(2)                            # Dedicated slots for metadata fetches

        self.lock = threading.RLock()
        self.active_tasks = set()
        self.global_pause = threading.Event()
        self.global_pause.set() # Default to RUNNING
        self.global_abort = False

    def get_semaphore(self, stage: str, model: str = None):
        # Normalize stage names (e.g., BR_ASS, BR_BURN, TR)
        if "TR" in stage: return self.tr_sem
        if "BR" in stage: return self.br_sem
        if "MR" in stage: return self.mr_sem
        if "TL" in stage:
            # Only 3.1-pro models are restricted to the 20-slot API semaphore
            if model and "3.1-pro" in model.lower():
                return self.api_sem
            else:
                return self.tl_flash_sem
        if "GD" in stage: return self.gd_sem
        return self.io_sem

    def acquire_slot(self, task: SubTask, stage: str, model: str = None):
        sem = self.get_semaphore(stage, model)
        sem.acquire()
        with self.lock:
            task.status = f"运行中 ({stage})"
            self.active_tasks.add(task.uid)

    def toggle_pause(self, engine):
        """Toggles global pause and propagates to all active processes."""
        with self.lock:
            if self.global_pause.is_set():
                self.global_pause.clear()
                # Suspend all active tasks
                for uid in self.active_tasks:
                    task = engine.task_map.get(uid)
                    if task and task.pid: ProcessTree.suspend(task.pid)
            else:
                self.global_pause.set()
                # Resume only those NOT individually suspended
                for uid in self.active_tasks:
                    task = engine.task_map.get(uid)
                    if task and task.pid and not task.is_paused:
                        ProcessTree.resume(task.pid)
        return True

    def release_slot(self, task: SubTask, stage: str, model: str = None):
        with self.lock:
            if task.uid in self.active_tasks:
                self.active_tasks.remove(task.uid)
        sem = self.get_semaphore(stage, model)
        sem.release()

# --- Engine & Workflow Orchestrator ---
class BatchEngine:
    """Manages task discovery, lifecycle, and stage transitions."""
    def __init__(self, output_dir=DEFAULT_OUTPUT_ROOT, state_file=None):
        self.output_dir = output_dir
        self.state_file = state_file or os.path.join(output_dir, "autosub_batch_v4_state.json")
        self.mgr = ResourceManager(CURRENT_DIR)
        self.queues: Dict[str, queue.Queue] = {
            "DL": queue.Queue(), "TR": queue.Queue(), "TL": queue.Queue(), "MR": queue.Queue(), "BR": queue.Queue(), "GD": queue.Queue()
        }
        self.task_map: Dict[int, SubTask] = {}
        self.url_map: Dict[str, SubTask] = {}
        self.lock = threading.RLock()

        # Load Global Settings
        self.settings = self._load_global_settings()

        # Cookie Discovery
        self.cookie_path = self._discover_cookies()

        # Node Discovery for JS Challenges
        self.node_exe = self._discover_node()

    def _discover_node(self):
        """Finds node for yt-dlp JS challenges."""
        path = shutil.which("node")
        if path: return path

        possible_paths = []
        if sys.platform == "win32":
            possible_paths = [
                os.path.join(TOOLS_DIR, "vdown", "node.exe"),
                r"C:\Program Files\nodejs\node.exe",
                r"D:\Program Files\nodejs\node.exe",
            ]
        elif sys.platform == "darwin":
            possible_paths = [
                "/opt/homebrew/bin/node",
                "/usr/local/bin/node",
                "/usr/bin/node",
            ]

        for p in possible_paths:
            if os.path.exists(p): return p
        return "node"

    def _discover_cookies(self):
        """Finds cookies.txt in prioritized locations."""
        # 1. Try settings.json
        try:
            if self.settings.get("cookie_path") and os.path.exists(self.settings["cookie_path"]):
                return self.settings["cookie_path"]
        except: pass

        # 2. Priority paths
        paths = [
            os.path.join(TOOLS_DIR, "vdown", "cookies.txt"),
            os.path.join(CURRENT_DIR, "cookies.txt"),
            r"D:\download\cookies.txt",
            r"D:\Downloads\cookies.txt",
            r"/Users/shanfu/cc/cookies.txt",
        ]
        for p in paths:
            if os.path.exists(p): return p
        return ""

    def _load_global_settings(self) -> Dict:
        """Loads model and style from autosub/settings.json or defaults.json."""
        autosub_dir = os.path.dirname(os.path.abspath(__file__))
        s_path = os.path.join(autosub_dir, "settings.json")
        d_path = os.path.join(autosub_dir, "defaults.json")

        target = s_path if os.path.exists(s_path) else d_path
        if os.path.exists(target):
            try:
                with open(target, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {"llm_model": "gemini-2.0-pro-exp-02-05", "style": "casual"}

    def get_task_workdir(self, title: str, vid_id: str, uid: int, sub_dir: Optional[str] = None):
        """Standardizes folder naming: '[xx] - Title [ID]'."""
        safe_title = re.sub(r'[\\/*?:"<>|]', '_', title).strip()
        root = os.path.join(self.output_dir, sub_dir) if sub_dir else self.output_dir
        return os.path.join(root, f"[{uid:02d}] - {safe_title} [{vid_id}]")

    def get_video_duration(self, file_path: str) -> float:
        """Helper to get duration using ffprobe."""
        try:
            cmd = [FFPROBE_EXE, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
            CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            out = subprocess.check_output(cmd, creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0).decode('utf-8').strip()
            return float(out)
        except: return 0.0

    def cleanup_zombie_processes(self, workdir: str):
        """Kills any yt-dlp or ffmpeg processes associated with the workdir (Active Cleanup)."""
        if not workdir or not os.path.exists(workdir): return
        try:
            import psutil
            for proc in psutil.process_iter(['name', 'cmdline']):
                try:
                    name = proc.info['name']
                    if not name: continue
                    name = name.lower()
                    cmdline = proc.info.get('cmdline', [])
                    if any(n in name for n in ['yt-dlp', 'ffmpeg', 'ffprobe', 'python']) and cmdline:
                        # For python processes, specifically check if they are running our tools in this workdir
                        if any(workdir.lower() in arg.lower() for arg in cmdline if arg):
                            logger.warning(f"Killing zombie process {proc.pid} ({name}) locking {workdir}")
                            proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except ImportError:
            logger.error("psutil not installed, skip zombie cleanup")

    def enqueue_task(self, task: SubTask, stage: str):
        """Thread-safe task queueing with deduplication."""
        with self.lock:
            if stage in task.queued_stages:
                return False
            task.queued_stages.add(stage)
            self.queues[stage].put(task)
            return True

    def add_task(self, url: str, title: Optional[str] = None, vid_id: Optional[str] = None, forced_uid: Optional[int] = None, sub_dir: Optional[str] = None):
        """Adds a task to the system, avoiding duplicates."""
        with self.lock:
            if url in self.url_map: return self.url_map[url]
            uid = forced_uid if forced_uid else (len(self.task_map) + 1)
            task = SubTask(uid=uid, url=url, title=title or "加载中...", sub_dir=sub_dir)
            if title and vid_id:
                task.workdir = self.get_task_workdir(task.title, vid_id, task.uid, sub_dir=sub_dir)

            self.task_map[uid] = task
            self.url_map[url] = task

        # If we already have a workdir, perform discovery immediately (OUTSIDE lock)
        if task.workdir:
            self.disk_truth_discovery(task)
        else:
            self.enqueue_task(task, "DL")
        return task

    def extract_video_id(self, url: str):
        """Extracts video ID for YouTube, X (Twitter), etc."""
        # YouTube ID (v=ID, be/ID, shorts/ID, live/ID, etc.)
        yt_match = re.search(r'(?:v=|be/|embed/|live/|shorts/|/)([a-zA-Z0-9_-]{11})(?:[?&]|$)', url)
        if yt_match: return yt_match.group(1).strip()

        # X (Twitter) ID (status/ID)
        x_match = re.search(r'status/(\d+)', url)
        if x_match: return x_match.group(1).strip()

        # Fallback: last segment of URL
        return url.rstrip('/').split('/')[-1].split('?')[0]

    def _parse_metadata(self, data, url):
        # Case 1: Single Video
        if 'entries' not in data:
            title = data.get("title", "未知视频")
            title = re.sub(r'[\r\n\t]+', ' ', title).strip()
            return {
                "playlist_title": None,
                "entries": [{"title": title, "id": data.get("id", self.extract_video_id(url)), "url": url}]
            }

        # Case 2: Playlist
        playlist_title = data.get("title", "未知播放列表")
        results = []
        for entry in data['entries']:
            if not entry: continue
            v_id = entry.get('id')
            v_title = entry.get('title', "未知视频")
            v_title = re.sub(r'[\r\n\t]+', ' ', v_title).strip()
            if v_id and v_title:
                results.append({
                    "title": v_title,
                    "id": v_id,
                    "url": f"https://www.youtube.com/watch?v={v_id}"
                })
        return {
            "playlist_title": playlist_title,
            "entries": results
        }

    def fetch_metadata(self, url: str, cookie_path: Optional[str] = None):
        """Extracts video metadata. Supports playlists by returning a list of dicts."""
        try:
            cookie_path = cookie_path or self.cookie_path

            # Use yt-dlp directly for robust playlist discovery
            cmd = [
                YTDLP_EXE,
                "--flat-playlist",
                "--dump-single-json",
                "--quiet",
                "--no-warnings"
            ]

            # Enhanced challenge solving for YouTube
            if "youtube.com" in url or "youtu.be" in url:
                cmd.extend(["--extractor-args", "youtube:player-client=tv"])
                cmd.extend(["--remote-components", "ejs:github"])
                if getattr(self, "node_exe", "node") != "node":
                    cmd.extend(["--js-runtime", f"node:{self.node_exe}"])
                else:
                    cmd.extend(["--js-runtime", "node"])

            cmd.append(url)

            # Handle cookies (including browser-based)
            resolved_cookies = cookie_path
            if resolved_cookies:
                if resolved_cookies.lower() in ["chrome", "firefox", "safari", "edge"]:
                    cmd.extend(["--cookies-from-browser", resolved_cookies.lower()])
                elif os.path.exists(resolved_cookies):
                    with use_temp_cookies(resolved_cookies) as temp_cookies:
                        if temp_cookies:
                            cmd.extend(["--cookies", temp_cookies])
                            out = subprocess.check_output(cmd, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == "win32" else 0).decode('utf-8', errors='ignore')
                            data = json.loads(out)
                            return self._parse_metadata(data, url)

            # Default run without cookies or if browser cookies used
            out = subprocess.check_output(cmd, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == "win32" else 0).decode('utf-8', errors='ignore')
            data = json.loads(out)
            return self._parse_metadata(data, url)

        except Exception as e:
            logger.error(f"Metadata fetch failed for {url}: {e}")
            # Fallback to single video attempt
            return {
                "playlist_title": None,
                "entries": [{"title": "未知视频", "id": self.extract_video_id(url), "url": url}]
            }

    def save_state(self):
        """Persists the entire state to the JSON file with retry logic for Windows locks."""
        with self.lock:
            data = {
                "tasks": [t.to_dict() for t in self.task_map.values()],
                "last_update": time.time()
            }

        temp_file = self.state_file + ".tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Robust rename for Windows (handles transient locks from indexers/sync tools)
            success = False
            for i in range(5):
                try:
                    os.replace(temp_file, self.state_file)
                    success = True
                    break
                except PermissionError:
                    if i < 4: time.sleep(0.1)
                    else: raise

            if not success and os.path.exists(temp_file):
                os.remove(temp_file)
        except Exception as e:
            # Silently log errors to the file to avoid TUI popups
            logger.debug(f"State save failed: {e}")

    def load_state(self):
        """Loads state from JSON and performs Disk-Truth discovery."""
        if not os.path.exists(self.state_file): return False
        try:
            with open(self.state_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            with self.lock:
                for t_dict in data.get("tasks", []):
                    t = SubTask.from_dict(t_dict)
                    self.task_map[t.uid] = t
                    self.url_map[t.url] = t
                    # Proactively clear queued stages on startup to avoid desync
                    t.queued_stages.clear()

            # Proactively check disk to resume or mark DONE (OUTSIDE lock)
            for t in self.task_map.values():
                self.disk_truth_discovery(t)
            return True
        except: return False

    def disk_truth_discovery(self, task: SubTask, requeue: bool = True):
        # Analyze work folder to determine the furthest completed stage (Self-Healing).
        if not task.workdir or not os.path.exists(task.workdir):
            if requeue:
                task.status = "排队中 (DL)"
                task.error = None
                self.enqueue_task(task, "DL")
            return

        # Helpers
        # 1. Check for final hardsub
        hardsub = [f for f in os.listdir(task.workdir) if "_hardsub.mp4" in f]
        if hardsub:
            # Check if sync is needed
            is_synced = os.path.exists(os.path.join(task.workdir, ".synced"))
            if getattr(self, 'gdsync_folder_id', None) and not is_synced:
                task.status = "排队中 (GD)"
                task.error = None
                task.pcts.update({"DL": 100.0, "TR": 100.0, "TL": 100.0, "MR": 100.0, "BR": 100.0, "GD": 0.0})
                if requeue: self.enqueue_task(task, "GD")
                return

            task.status = "完成"
            for s in task.pcts: task.pcts[s] = 100.0
            with self.lock:
                task.queued_stages.clear()
            return

        # 1.5. Check for Transcription Progress (Pre-emptive)
        # This helps keep the UI progress consistent on startup
        checkpoint_path = os.path.join(task.workdir, "transcribe_state.json")
        if os.path.exists(checkpoint_path):
            try:
                with open(checkpoint_path, 'r', encoding='utf-8') as f:
                    segments = json.load(f).get('segments', [])
                    if segments:
                        last_end = segments[-1].get('end', 0)
                        # We need duration to calculate percentage
                        # Heuristic: find the video file
                        vids = [f for f in os.listdir(task.workdir) if f.endswith((".mp4", ".mkv", ".webm")) and "_hardsub" not in f]
                        if vids:
                            dur = self.get_video_duration(os.path.join(task.workdir, vids[0]))
                            if dur > 0:
                                p = min(max(0.0, (last_end / dur) * 100.0), 99.9)
                                task.pcts["TR"] = round(p, 1)
            except: pass

        # 2. Check for Bilingual SRT
        bi_srt = [f for f in os.listdir(task.workdir) if ".bi.srt" in f]
        if bi_srt:
            task.status = "排队中 (BR)"
            task.error = None
            task.pcts.update({"DL": 100.0, "TR": 100.0, "TL": 100.0, "MR": 100.0})
            if requeue: self.enqueue_task(task, "BR")
            return

        # 3. Check for CN/ZH SRT
        zh_srt = [f for f in os.listdir(task.workdir) if re.search(r'(\.cn|\.zh)\.srt$', f)]
        if zh_srt:
            task.status = "排队中 (MR)"
            task.error = None
            task.pcts.update({"DL": 100.0, "TR": 100.0, "TL": 100.0})
            if requeue: self.enqueue_task(task, "MR")
            return

        # 4. Check for Source SRT (English)
        en_srt = [f for f in os.listdir(task.workdir) if f.endswith(".srt") and not re.search(r'(\.zh|\.cn|\.bi)\.srt$', f)]
        if en_srt:
            task.status = "排队中 (TL)"
            task.error = None
            task.pcts.update({"DL": 100.0, "TR": 100.0})
            if requeue: self.enqueue_task(task, "TL")
            return

        # 5. Check for Raw Video
        raw_vid = [f for f in os.listdir(task.workdir) if f.endswith((".mp4", ".mkv", ".webm")) and "_hardsub" not in f]
        if raw_vid:
            # Sync title from disk if currently unknown
            if task.title == "未知视频" or not task.title or "youtu.be" in task.title:
                fn = os.path.splitext(raw_vid[0])[0]
                m_title = re.split(r'\s\[', fn)[0].strip()
                if m_title: task.title = m_title

            task.status = "排队中 (TR)"
            task.error = None
            task.pcts.update({"DL": 100.0})
            if requeue: self.enqueue_task(task, "TR")
            return

        if requeue:
            task.status = "排队中 (DL)"
            task.error = None
            self.enqueue_task(task, "DL")

    def requeue_stalled_tasks(self):
        """Self-Healing: Identifies tasks stuck in 'Queued' status but not in memory queues."""
        with self.lock:
            for task in self.task_map.values():
                if "排队中" in task.status and not task.is_paused:
                    # Extract target stage from "排队中 (TR)"
                    stage_match = re.search(r'\(([^)]+)\)', task.status)
                    if stage_match:
                        target_stage = stage_match.group(1)
                        if target_stage not in task.queued_stages:
                            logger.info(f"Self-Healing | Re-enqueuing orphaned task {task.uid} for stage {target_stage}")
                            self.enqueue_task(task, target_stage)

    def run_stage(self, task: SubTask, stage: str, cmd: List[str], model: str = None, final_pct: Optional[float] = 100.0):
        """Executes a component-level stage with progress tracking."""
        if not task.workdir:
            task.error = "No workdir defined"
            return False

        # Pre-flight cleanup
        if stage in ["DL", "TR", "BR_ASS", "BR_BURN"]:
            self.cleanup_zombie_processes(task.workdir)

        # 1. Acquire concurrency slot
        with self.lock:
            task.status = f"等待中 ({stage})"
        self.mgr.acquire_slot(task, stage, model)

        # Determine log file
        log_file = os.path.join(task.workdir, "workflow.log") if task.workdir else None

        try:
            self.mgr.global_pause.wait() # Respect global pause

            # 2. Cleanup task error before starting
            task.error = None
            logger.info(f"Task {task.uid} | Stage {stage} | Starting | Cmd: {' '.join(cmd)}")

            with open(log_file, "a", encoding="utf-8") as f_log:
                f_log.write(f"\n\n--- [{datetime.now().isoformat()}] STAGE: {stage} ---\n")
                f_log.write(f"COMMAND LIST: {json.dumps(cmd, ensure_ascii=False)}\n")
                f_log.write(f"COMMAND: {' '.join(cmd)}\n")
                f_log.flush()

                p = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=task.workdir,
                    encoding='utf-8',
                    errors='replace',
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == "win32" else 0
                )
                task.pid = p.pid

                # 3. Stream output and parse progress
                for line in p.stdout:
                    if self.mgr.global_abort:
                        ProcessTree.kill(p.pid)
                        break

                    # Log every line to task log
                    f_log.write(line)
                    f_log.flush()

                    line = line.strip()
                    if not line: continue

                    # Progress Regex
                    percent = None
                    if "Progress:" in line:
                        m = re.search(r'Progress:\s*([\d\.]+)%', line)
                        if m: percent = float(m.group(1))
                    elif "[download]" in line and "%" in line:
                        m = re.search(r'\[download\]\s*([\d\.]+)%', line)
                        if m: percent = float(m.group(1))

                    if percent is not None:
                        task.pcts[stage.split("_")[0]] = round(percent, 1) # Support 1 decimal place

                p.wait()
                ret = p.returncode
                task.pid = None

                if ret != 0 and not self.mgr.global_abort:
                    task.status = f"失败 ({stage})"
                    task.error = f"进程退出码: {ret}"
                    logger.error(f"Task {task.uid} | Stage {stage} | Failed with code {ret}")
                    f_log.write(f"\n--- FAILED with code {ret} ---\n")
                    return False

                if final_pct is not None:
                    task.pcts[stage.split("_")[0]] = final_pct
                logger.info(f"Task {task.uid} | Stage {stage} | Success")
                f_log.write(f"\n--- SUCCESS ---\n")
                return True
        except Exception as e:
            task.status = f"失败 ({stage})"
            task.error = str(e)
            logger.exception(f"Task {task.uid} | Stage {stage} | Exception: {e}")
            if log_file:
                with open(log_file, "a", encoding="utf-8") as f_log:
                    f_log.write(f"\nEXCEPTION: {str(e)}\n")
            return False
        finally:
            # 4. ALWAYS release the concurrency slot
            self.mgr.release_slot(task, stage, model)

    def worker(self, stage: str):
        """Generic worker thread for any given stage."""
        logger.info(f"Worker {threading.current_thread().name} started for stage {stage}")
        while not self.mgr.global_abort:
            try:
                try:
                    task = self.queues[stage].get(timeout=1)
                except queue.Empty:
                    continue

                # Immediately remove from queued_stages when picked up
                with self.lock:
                    if stage in task.queued_stages:
                        task.queued_stages.remove(stage)

                # Resumability & Pause check
                if task.status == "完成" or (task.is_paused and not self.mgr.global_pause.is_set()):
                    self.queues[stage].task_done()
                    continue

                # Check for global retry limit
                if task.retries >= 3: # Hard limit for auto-retries (Reduced to 3 per user request)
                    task.status = "失败 (重试过多)"
                    self.queues[stage].task_done()
                    continue

                # Stage-specific logic
                success = False
                if stage == "DL":
                    if not task.workdir:
                        # Dedicated metadata semaphore to avoid blocking download slots
                        with self.mgr.meta_sem:
                            meta_res = self.fetch_metadata(task.url)
                            info = meta_res['entries'][0]
                            task.title = info['title']
                            task.workdir = self.get_task_workdir(task.title, info['id'], task.uid, sub_dir=task.sub_dir)

                    # Discovery check (without requeueing)
                    orig_status = task.status
                    self.disk_truth_discovery(task, requeue=False)
                    if "排队中" in task.status and "DL" not in task.status:
                        # Discovery found we should be in a later stage
                        # disk_truth_discovery already updated status but didn't enqueue because requeue=False
                        self.enqueue_task(task, task.status.split("(")[1].strip(")"))
                        self.queues[stage].task_done()
                        continue

                    # Ensure status is reset if discovery didn't move it
                    task.status = orig_status

                    os.makedirs(task.workdir, exist_ok=True)
                    cookie_path = self.cookie_path
                    cmd = list(VDOWN_CMD) + [task.url, cookie_path, task.workdir, "--title", task.title]
                    if getattr(self, 'quick_mode', False):
                        cmd.append("--write-subs")
                    success = self.run_stage(task, "DL", cmd)
                    if success:
                        # --- Post-DL Sync: Update Title & Folder Name ---
                        vids = [f for f in os.listdir(task.workdir) if f.endswith((".mp4", ".mkv", ".webm")) and "_hardsub" not in f]
                        if vids:
                            # Extract real title from filename "Title [ID] [1080p].mp4"
                            fn = os.path.splitext(vids[0])[0]
                            # Standard vdown pattern: Match everything before the first " ["
                            m_title = re.split(r'\s\[', fn)[0].strip()
                            if m_title and (task.title == "未知视频" or not task.title or "youtu.be" in task.title):
                                old_workdir = task.workdir
                                task.title = m_title
                                vid_id = self.extract_video_id(task.url)

                                new_workdir = self.get_task_workdir(task.title, vid_id, task.uid, sub_dir=task.sub_dir)
                                if old_workdir != new_workdir and os.path.exists(old_workdir):
                                    try:
                                        # Safety check: is it the same root?
                                        if os.path.dirname(old_workdir) == os.path.dirname(new_workdir):
                                            os.rename(old_workdir, new_workdir)
                                            task.workdir = new_workdir
                                            logger.info(f"Task {task.uid} | Renamed: {os.path.basename(old_workdir)} -> {os.path.basename(new_workdir)}")

                                            # Also rename the file inside to match naming convention ([xx] - Title)
                                            # We find the video file and rename it to the folder's name prefix style
                                            vids = [f for f in os.listdir(task.workdir) if f.endswith((".mp4", ".mkv", ".webm")) and "_hardsub" not in f]
                                            if vids:
                                                old_file = os.path.join(task.workdir, vids[0])
                                                ext = os.path.splitext(vids[0])[1]
                                                new_filename = f"{os.path.basename(task.workdir)}{ext}"
                                                new_file = os.path.join(task.workdir, new_filename)
                                                if not os.path.exists(new_file):
                                                    os.rename(old_file, new_file)
                                                    logger.info(f"Task {task.uid} | File Renamed: {vids[0]} -> {new_filename}")
                                    except Exception as e:
                                        logger.warning(f"Task {task.uid} | Rename failed: {e}")

                        task.retries = 0 # Reset on success
                        self.enqueue_task(task, "TR")
                    else:
                        task.retries += 1
                        # Optional: Auto-requeue DL once if it's a transient network error
                        if task.retries < 3:
                            logger.info(f"Task {task.uid} | Stage DL | Retrying ({task.retries}/3)...")
                            self.enqueue_task(task, "DL")

                elif stage == "TR":
                    vids = [f for f in os.listdir(task.workdir) if f.endswith((".mp4", ".mkv", ".webm")) and "_hardsub" not in f]
                    if vids:
                        target_vid = os.path.join(task.workdir, vids[0])
                        cmd = list(TRANSCRIBER_CMD) + [target_vid, "--output", task.workdir, "--no-gui"]
                        if getattr(self, 'quick_mode', False):
                            cmd.append("--quick")
                        success = self.run_stage(task, "TR", cmd)
                        if success:
                            task.retries = 0
                            self.enqueue_task(task, "TL")
                        else:
                            # 错误发生，利用“磁盘真相”检查一下是否其实已经干完了（处理幻影错误）
                            self.disk_truth_discovery(task, requeue=False)
                            if "排队中" in task.status and "TR" not in task.status:
                                logger.info(f"Task {task.uid} | TR 幻影错误拦截，已通过磁盘验证进入下一阶段")
                                task.retries = 0 # 视为成功
                            elif task.retries < 3:
                                task.retries += 1
                                logger.warning(f"Task {task.uid} | TR 报错，正在尝试自动断点重试 ({task.retries}/3)...")
                                self.enqueue_task(task, "TR")
                            else:
                                task.status = "失败 (TR重试过多)"
                    else:
                        task.error = "未找到视频文件"
                        task.status = "失败"

                elif stage == "TL":
                    srts = [f for f in os.listdir(task.workdir) if f.endswith(".srt") and not re.search(r'(\.zh|\.cn|\.bi)\.srt$', f)]
                    if srts:
                        target_srt = os.path.join(task.workdir, srts[0])
                        model = self.settings.get("llm_model", "gemini-3-flash-preview")
                        style = self.settings.get("style", "casual")
                        cmd = list(SMART_TRANSLATE_CMD) + [target_srt, "--model", model, "--style", style]
                        success = self.run_stage(task, "TL", cmd, model=model)
                        if success:
                            task.retries = 0
                            self.enqueue_task(task, "MR")
                        else:
                            if task.retries < 3:
                                task.retries += 1
                                logger.warning(f"Task {task.uid} | TL 报错，正在尝试自动重试 ({task.retries}/3)...")
                                self.enqueue_task(task, "TL")
                            else:
                                task.status = "失败 (TL重试过多)"
                    else:
                        task.error = "未找到源字幕"
                        task.status = "失败"

                elif stage == "MR":
                    en_srt = [f for f in os.listdir(task.workdir) if f.endswith(".srt") and not re.search(r'(\.zh|\.cn|\.bi)\.srt$', f)]
                    zh_srt = [f for f in os.listdir(task.workdir) if re.search(r'(\.cn|\.zh)\.srt$', f)]
                    if en_srt and zh_srt:
                        cmd = list(SUBTRANSLATOR_CMD) + ["merge", os.path.join(task.workdir, en_srt[0]), "--translated-file", os.path.join(task.workdir, zh_srt[0])]
                        success = self.run_stage(task, "MR", cmd)
                        if success:
                            task.retries = 0
                            self.enqueue_task(task, "BR")
                        else:
                            if task.retries < 3:
                                task.retries += 1
                                logger.warning(f"Task {task.uid} | MR 报错，正在尝试自动重试 ({task.retries}/3)...")
                                self.enqueue_task(task, "MR")
                            else:
                                task.status = "失败 (MR重试过多)"

                elif stage == "BR":
                    bi_srt = [f for f in os.listdir(task.workdir) if ".bi.srt" in f]
                    raw_vid = [f for f in os.listdir(task.workdir) if f.endswith((".mp4", ".mkv", ".webm")) and "_hardsub" not in f]
                    if bi_srt and raw_vid:
                        v_path = os.path.join(task.workdir, raw_vid[0])
                        s_path = os.path.join(task.workdir, bi_srt[0])
                        a_path = s_path.replace(".srt", ".ass")
                        out_v = v_path.replace(os.path.splitext(v_path)[1], "_hardsub" + os.path.splitext(v_path)[1])

                        # Reset progress for BR stage at start
                        task.pcts["BR"] = 0.0

                        success = False
                        ass_cmd = list(SRT2ASS_CMD) + [s_path, a_path, "--layout", "bilingual"]
                        if self.run_stage(task, "BR_ASS", ass_cmd, final_pct=1.0):
                            burn_cmd = list(BURNSUB_CMD) + [v_path, a_path, out_v, "--headless"]
                            if self.run_stage(task, "BR_BURN", burn_cmd):
                                task.pcts["BR"] = 100.0
                                task.retries = 0
                                if getattr(self, 'gdsync_folder_id', None):
                                    self.enqueue_task(task, "GD")
                                else:
                                    task.status = "完成"
                                success = True

                        if not success:
                            # 检查是否其实压制成功了（处理 ffmpeg 在最后时刻的崩溃）
                            self.disk_truth_discovery(task, requeue=False)
                            if (task.status == "完成" or "排队中 (GD)" in task.status) and "BR" not in task.status:
                                logger.info(f"Task {task.uid} | BR 幻影错误拦截，已通过磁盘验证完成环节")
                                task.retries = 0
                            elif task.retries < 3:
                                task.retries += 1
                                logger.warning(f"Task {task.uid} | BR 报错，正在尝试自动重试 ({task.retries}/3)...")
                                self.enqueue_task(task, "BR")
                            else:
                                task.status = "失败 (BR重试过多)"

                elif stage == "GD":
                    # Call sync.py
                    sync_script = os.path.join(PROJECT_ROOT, ".agents", "skills", "google-drive-sync", "scripts", "sync.py")
                    if os.path.exists(sync_script):
                        # Narrowed sync scope: Sync only the relevant project/task sub-directory to avoid 'Projects' nesting
                        folder_id = self.gdsync_folder_id
                        sync_dir = os.path.join(self.output_dir, task.sub_dir) if task.sub_dir else task.workdir
                        cmd = [sys.executable, sync_script, "--local-dir", sync_dir, "--remote-id", folder_id, "--wrap-folder", "--headless"]
                        success = self.run_stage(task, "GD", cmd)
                        if success:
                            # Touch .synced marker
                            with open(os.path.join(task.workdir, ".synced"), "w") as f:
                                f.write(str(time.time()))
                            task.status = "完成"
                            task.retries = 0
                        else:
                            task.retries += 1
                    else:
                        task.error = "未找到同步脚本 sync.py"
                        task.status = "失败 (GD)"

                self.queues[stage].task_done()
            except Exception as e:
                logger.exception(f"Worker {stage} encountered an unexpected error: {e}")
                time.sleep(1)

    def start_workers(self):
        # Spawning threads dynamically based on hardware limits + a small buffer
        limits = {
            "DL": self.mgr.hw.get("io_max", 6),
            "TR": self.mgr.hw.get("tr_max", 2),
            "TL": 10,  # Translators are predominantly API-bound
            "MR": self.mgr.hw.get("io_max", 6),
            "BR": self.mgr.hw.get("br_max", 2),
            "GD": 6
        }
        for s, count in limits.items():
            # Ensure at least 4 threads for key stages even on low-end hardware for UI responsiveness
            thread_count = max(4, count)
            for _ in range(thread_count):
                threading.Thread(target=self.worker, args=(s,), daemon=True).start()

# --- Dashboard TUI ---
class Dashboard:
    def __init__(self, engine: BatchEngine):
        self.engine = engine
        self.console = Console()
        self.scroll_idx = 0
        self.cmd_buffer = ""

    def make_progress_bar(self, pcts: Dict[str, float]):
        """Creates a compact visual progress bar for all 5 stages with strict alignment."""
        parts = []
        # Use full-width Chinese characters for labels to ensure consistent 2-char width
        stages = [("下", "DL"), ("录", "TR"), ("译", "TL"), ("合", "MR"), ("压", "BR")]
        if getattr(self.engine, 'gdsync_folder_id', None):
            stages.append(("传", "GD"))

        for label, key in stages:
            val = pcts.get(key, 0.0)
            width = 4 if len(stages) > 5 else 5 # Shrink to fit if more stages
            filled = int(val / 100 * width)
            color = "green" if val >= 100 else "cyan" if val > 0 else "grey37"
            bar = f"[{color}]" + "█" * filled + "░" * (width - filled) + "[/]"
            # Format percentage as 5-character fixed width (e.g., '100.0', ' 50.4', '  0.0')
            parts.append(f"{label}:{bar}{val:>5.1f}%")
        return " ".join(parts)

    def generate_layout(self):
        width, height = self.console.size
        # Dynamic row count: Header (3) + Footer (4) + Table Padding (4)
        max_rows = max(5, height - 11)

        table = Table(box=box.MINIMAL_DOUBLE_HEAD, expand=True, border_style="grey37")
        table.add_column("UID", width=4, justify="center", style="bold", no_wrap=True)
        # Adaptive title: No ratio, no truncation, to show full text
        table.add_column("视频标题", no_wrap=False)
        table.add_column("状态", width=14, justify="center", no_wrap=True)
        pb_width = 100 if getattr(self.engine, 'gdsync_folder_id', None) else 80
        table.add_column("进度 (下/录/译/合/压" + ("/传" if getattr(self.engine, 'gdsync_folder_id', None) else "") + ")", width=pb_width, justify="center", no_wrap=True)

        with self.engine.lock:
            tasks = list(self.engine.task_map.values())
            tasks.sort(key=lambda x: x.uid)

            # Ensure scroll index is within bounds
            if self.scroll_idx >= len(tasks) and self.scroll_idx > 0: self.scroll_idx = 0

            visible_tasks = tasks[self.scroll_idx : self.scroll_idx + max_rows]

            for t in visible_tasks:
                # Determine refined status and color
                is_globally_paused = not self.engine.mgr.global_pause.is_set()
                is_task_paused = t.is_paused or is_globally_paused

                status_text = t.status
                status_color = "white"

                if t.status == "完成":
                    status_color = "green"
                elif t.status.startswith("失败"):
                    status_color = "red"
                elif "运行中" in t.status:
                    if is_task_paused:
                        # Extract stage from "运行中 (TR)" -> "已暂停 (TR)"
                        stage_match = re.search(r'\(([^)]+)\)', t.status)
                        stage_info = stage_match.group(1) if stage_match else "..."
                        status_text = f"已暂停 ({stage_info})"
                        status_color = "yellow"
                    else:
                        status_color = "cyan" # Use cyan (bright blue) for active tasks
                elif "排队中" in t.status:
                    status_color = "grey62"

                table.add_row(
                    str(t.uid),
                    t.title,
                    f"[{status_color}]{status_text}[/{status_color}]",
                    self.make_progress_bar(t.pcts)
                )

        layout = Layout()
        layout.split(
            Layout(name="body"),
            Layout(name="footer", size=3)
        )

        layout["body"].update(table)

        help_msg = "P:全局暂停 | S+ID:挂起任务 | R+ID:重启环节 | Q:退出 | ↑/↓:滚动"
        if self.cmd_buffer: help_msg = f"[bold yellow]输入: {self.cmd_buffer}[/bold yellow] | " + help_msg

        layout["footer"].update(Align.center(help_msg))
        return layout

def interactive_loop(engine: BatchEngine, dash: Dashboard):
    cmd_mode = None # 'S' or 'R'
    id_buffer = ""

    while not engine.mgr.global_abort:
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch in [b'\x00', b'\xe0']: # Special keys
                sc = msvcrt.getch()
                if sc == b'H': dash.scroll_idx = max(0, dash.scroll_idx - 1)
                elif sc == b'P': dash.scroll_idx = min(len(engine.task_map) - 1, dash.scroll_idx + 1)
                continue

            key = ch.decode('utf-8', errors='ignore').lower()
            if not cmd_mode:
                if key == 'q': engine.mgr.global_abort = True
                elif key == 'p': engine.mgr.toggle_pause(engine)
                elif key == 's':
                    cmd_mode = 'S'
                    dash.cmd_buffer = "挂起任务 ID: "
                elif key == 'r':
                    cmd_mode = 'R'
                    dash.cmd_buffer = "重启任务 ID: "
            else:
                if key.isdigit():
                    id_buffer += key
                    dash.cmd_buffer += key
                elif ch == b'\r': # Enter
                    if id_buffer:
                        uid = int(id_buffer)
                        task = engine.task_map.get(uid)
                        if task:
                            if cmd_mode == 'S':
                                task.is_paused = not task.is_paused
                                if task.pid:
                                    if task.is_paused: ProcessTree.suspend(task.pid)
                                    else: ProcessTree.resume(task.pid)
                            elif cmd_mode == 'R':
                                with engine.lock:
                                    if task.pid: ProcessTree.kill(task.pid)
                                    task.status = "重置中..."
                                    task.error = None
                                    task.is_paused = False
                                    engine.disk_truth_discovery(task)
                    cmd_mode, id_buffer, dash.cmd_buffer = None, "", ""
                elif ch == b'\x1b': # Esc
                    cmd_mode, id_buffer, dash.cmd_buffer = None, "", ""

        time.sleep(0.05)

# --- CLI & Main ---
def main():
    parser = argparse.ArgumentParser(description="AutoSub Batch Pro v4")
    parser.add_argument("--urls", nargs="+", help="YouTube URLs or Playlists")
    parser.add_argument("--file", help="Text file with URLs")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_ROOT, help="Output directory")
    parser.add_argument("--cookies", default=r"D:\Downloads\cookies.txt", help="Path to cookies.txt")
    parser.add_argument("--gdsync", nargs="?", const="18iAFFSuHQmZlxVN0dri1Gbje9SmpS96f", help="Sync results to Google Drive (opt: folder_id)")
    parser.add_argument("--exclude", help="Comma-separated indices to exclude (1-based, playlist order)")
    parser.add_argument("--quick", action="store_true", help="Experimental: Quick Transcribe (YouTube Subs + LLM)")
    parser.add_argument("--separate", action="store_true", help="Use playlist titles as subdirectories")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    engine = BatchEngine(output_dir=args.output)
    engine.cookie_path = args.cookies # Store cookie path in engine
    engine.gdsync_folder_id = args.gdsync # Enabled if not None
    engine.quick_mode = args.quick

    # 1. Load History
    engine.load_state()

    # 2. Add New Inputs
    input_urls = []
    if args.urls: input_urls.extend(args.urls)
    if args.file and os.path.exists(args.file):
        with open(args.file, "r", encoding="utf-8-sig") as f:
            input_urls.extend([l.strip() for l in f if l.strip()])

    exclude_indices = []
    if args.exclude:
        exclude_indices = [int(i.strip()) for i in args.exclude.split(",") if i.strip().isdigit()]

    for url in input_urls:
        meta_res = engine.fetch_metadata(url, cookie_path=engine.cookie_path)
        playlist_title = meta_res['playlist_title']
        sub_dir = None
        if args.separate and playlist_title:
            # Sanitize sub_dir: remove underscores, use spaces
            sub_dir = re.sub(r'[\\/*?:"<>|_]', ' ', playlist_title).strip()

        for idx, m in enumerate(meta_res['entries'], 1):
            if idx in exclude_indices:
                logger.info(f"Excluding index {idx}: {m['title']}")
                continue

            # For multiple playlists in one batch, UIDs should be global
            # add_task will handle global UIDs if not forced
            engine.add_task(m['url'], title=m['title'], vid_id=m['id'], sub_dir=sub_dir)

    # 3. Initial Save and Run TUI
    engine.save_state()
    engine.start_workers()
    dash = Dashboard(engine)

    threading.Thread(target=interactive_loop, args=(engine, dash), daemon=True).start()

    with Live(dash.generate_layout(), refresh_per_second=2, screen=True) as live:
        last_log_time = 0
        last_healing_time = 0
        last_save_time = 0
        done_start_time = None

        while not engine.mgr.global_abort:
            live.update(dash.generate_layout())

            # Check for Auto-Exit: All tasks terminal and no active workers
            all_finished = all(t.status in ["完成", "跳过", "失败 (重试过多)"] for t in engine.task_map.values())
            if all_finished and not engine.mgr.active_tasks:
                if done_start_time is None:
                    done_start_time = time.time()
                elif time.time() - done_start_time > 10: # Auto-exit after 10s of silence
                    logger.info("所有任务已圆满完成。系统将在 10 秒后自动退出...")
                    engine.mgr.global_abort = True
                    break
            else:
                done_start_time = None

            # Reduce save frequency to every 5s to avoid WinError 5 collisions
            if time.time() - last_save_time > 5:
                engine.save_state()
                last_save_time = time.time()

            # Periodically perform self-healing (every 15s)
            if time.time() - last_healing_time > 15:
                engine.requeue_stalled_tasks()
                last_healing_time = time.time()

            # Periodically log resource status
            if time.time() - last_log_time > 30:
                tr_val = engine.mgr.tr_sem._value
                br_val = engine.mgr.br_sem._value
                a_val = engine.mgr.api_sem._value
                f_val = engine.mgr.tl_flash_sem._value
                i_val = engine.mgr.io_sem._value
                logger.info(f"Resource Status | TR: {tr_val} | BR: {br_val} | API: {a_val} | Flash: {f_val} | IO: {i_val} | Active: {len(engine.mgr.active_tasks)}")
                last_log_time = time.time()

            time.sleep(0.5)

    print("系统退出中...")

if __name__ == "__main__":
    main()