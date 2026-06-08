import sys
import os
import subprocess
import threading
import queue
import re
import tkinter as tk
from tkinter import ttk

# --- Styling Constants ---
COLOR_BG = "#0f172a"  # Slate 900
COLOR_FG = "#f8fafc"  # Slate 50
COLOR_ACCENT = "#06b6d4"  # Cyan 500
COLOR_ACCENT_ALT = "#d946ef"  # Fuchsia 500
FONT_MAIN = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 11, "bold")

class VdownGUI:
    def __init__(self, root, video_url, cookies=None, out_dir=None):
        self.root = root
        self.root.title("vdown - 下载进度")
        self.root.geometry("500x180")
        self.root.configure(bg=COLOR_BG)
        self.root.resizable(False, False)

        self.video_url = video_url
        self.cookies = cookies
        self.out_dir = out_dir
        self.queue = queue.Queue()

        # Center on screen
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'+{x}+{y}')

        self.setup_ui()
        self.start_download()

    def setup_ui(self):
        # Header
        self.title_label = tk.Label(
            self.root, text="正在准备下载...", font=FONT_BOLD,
            bg=COLOR_BG, fg=COLOR_ACCENT, wraplength=450, justify="center"
        )
        self.title_label.pack(pady=(20, 10))

        # Progress Bar Style
        style = ttk.Style()
        style.theme_use('default')
        style.configure(
            "Cyan.Horizontal.TProgressbar",
            troughcolor="#1e293b",
            background=COLOR_ACCENT,
            thickness=12,
            borderwidth=0
        )

        self.progress_bar = ttk.Progressbar(
            self.root, orient="horizontal", length=400,
            mode="determinate", style="Cyan.Horizontal.TProgressbar"
        )
        self.progress_bar.pack(pady=10)

        self.status_label = tk.Label(
            self.root, text="进度: 0%", font=FONT_MAIN,
            bg=COLOR_BG, fg=COLOR_FG
        )
        self.status_label.pack()

    def start_download(self):
        # Build Command
        tool_dir = os.path.dirname(os.path.abspath(__file__))
        download_script = os.path.join(tool_dir, "download.py")

        cmd = [sys.executable, download_script, self.video_url]
        if self.cookies:
            cmd.append(self.cookies)
        else:
            cmd.append(" ") # Use space for PS alignment

        if self.out_dir:
            cmd.append(self.out_dir)

        # Thread for running subprocess
        self.thread = threading.Thread(target=self.run_subprocess, args=(cmd,), daemon=True)
        self.thread.start()

        # Polling the queue
        self.root.after(100, self.process_queue)

    def run_subprocess(self, cmd):
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )

            for line in process.stdout:
                self.queue.put(("log", line))
                # Match progress
                match = re.search(r'Progress: (\d+\.?\d*)%', line)
                if match:
                    self.queue.put(("progress", float(match.group(1))))

                # Capture title from logs
                if "Title:" in line:
                    title = line.split("Title:", 1)[1].strip()
                    self.queue.put(("title", title))

            process.wait()
            self.queue.put(("done", process.returncode))
        except Exception as e:
            self.queue.put(("error", str(e)))

    def process_queue(self):
        try:
            while True:
                msg_type, msg_val = self.queue.get_nowait()
                if msg_type == "progress":
                    self.progress_bar["value"] = msg_val
                    self.status_label.config(text=f"进度: {msg_val}%")
                elif msg_type == "title":
                    self.title_label.config(text=msg_val)
                elif msg_type == "log":
                    pass
                elif msg_type == "done":
                    if msg_val == 0:
                        self.title_label.config(text="✅ 下载完成", fg="#10b981") # Emerald 500
                        self.status_label.config(text="任务成功结束")
                        self.root.after(3000, self.root.destroy)
                    else:
                        self.title_label.config(text="❌ 下载失败", fg="#ef4444") # Red 500
                        self.status_label.config(text=f"已退出，代码: {msg_val}")
                        # Keep open for error viewing
                elif msg_type == "error":
                    self.title_label.config(text="⚠ 启动错误", fg="#f59e0b") # Amber 500
                    self.status_label.config(text=msg_val)
        except queue.Empty:
            pass

        self.root.after(100, self.process_queue)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python vdown_gui.py <URL> [cookies_file] [out_dir]")
        sys.exit(1)

    url = sys.argv[1]
    cookies = sys.argv[2] if len(sys.argv) > 2 else None
    out_dir = sys.argv[3] if len(sys.argv) > 3 else None

    root = tk.Tk()
    app = VdownGUI(root, url, cookies, out_dir)
    root.mainloop()