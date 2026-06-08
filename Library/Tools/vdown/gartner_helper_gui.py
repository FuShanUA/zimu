import tkinter as tk
from tkinter import ttk, scrolledtext
import subprocess
import threading
import sys
import os
import re
import time

class GartnerHelperGUI:
    def __init__(self, root, gartner_url=None):
        self.root = root
        self.root.title("Gartner Video Downloader - Manual Helper")
        self.root.geometry("700x600")
        self.gartner_url = gartner_url
        self.download_process = None
        self.monitoring = False

        # Main container
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Instructions section
        instructions_label = ttk.Label(main_frame, text="📋 Manual URL Extraction Steps", font=('Arial', 12, 'bold'))
        instructions_label.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        instructions_text = """1. Open your browser and go to the Gartner webinar page
2. Press F12 to open Developer Tools
3. Click the "Network" tab (not Elements!)
4. In the filter box at the top, type: m3u8
5. Click Play on the video
6. Look for a request with ".m3u8" in the URL
7. Right-click on it → Copy → Copy URL
8. Paste the URL below and click Download"""

        instructions_box = tk.Text(main_frame, height=10, width=80, wrap=tk.WORD,
                                   bg='#f0f0f0', relief=tk.FLAT, padx=10, pady=10)
        instructions_box.insert('1.0', instructions_text)
        instructions_box.config(state=tk.DISABLED)
        instructions_box.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 15))

        # URL input section
        url_label = ttk.Label(main_frame, text="📎 Paste the .m3u8 URL here:", font=('Arial', 10, 'bold'))
        url_label.grid(row=2, column=0, sticky=tk.W, pady=(0, 5))

        self.url_entry = ttk.Entry(main_frame, width=80)
        self.url_entry.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        # Download button
        self.download_btn = ttk.Button(main_frame, text="⬇ Download Video", command=self.start_download)
        self.download_btn.grid(row=4, column=0, columnspan=2, pady=(0, 15))

        # Progress section
        progress_label = ttk.Label(main_frame, text="📊 Download Progress", font=('Arial', 10, 'bold'))
        progress_label.grid(row=5, column=0, sticky=tk.W, pady=(0, 5))

        self.progress_text = scrolledtext.ScrolledText(main_frame, height=12, width=80,
                                                       wrap=tk.WORD, state=tk.DISABLED)
        self.progress_text.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Status bar
        self.status_label = ttk.Label(main_frame, text="Ready. Waiting for URL...",
                                      relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))

        # Configure grid weights
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(6, weight=1)

        # If Gartner URL provided, show it in status
        if self.gartner_url:
            self.log_message(f"Detected Gartner URL: {self.gartner_url}\n")
            self.log_message("Follow the steps above to extract the video URL.\n")

    def log_message(self, message):
        self.progress_text.config(state=tk.NORMAL)
        self.progress_text.insert(tk.END, message)
        self.progress_text.see(tk.END)
        self.progress_text.config(state=tk.DISABLED)

    def start_download(self):
        url = self.url_entry.get().strip()
        if not url:
            self.status_label.config(text="❌ Please paste a URL first!")
            return

        if '.m3u8' not in url:
            self.status_label.config(text="⚠ Warning: URL doesn't contain .m3u8 - are you sure this is correct?")

        self.download_btn.config(state=tk.DISABLED)
        self.status_label.config(text="⏳ Starting download...")
        self.log_message(f"\n{'='*60}\n")
        self.log_message(f"Starting download: {url}\n")
        self.log_message(f"{'='*60}\n\n")

        # Start download in background thread
        thread = threading.Thread(target=self.run_download, args=(url,), daemon=True)
        thread.start()

    def run_download(self, url):
        download_root = os.path.join(os.path.splitdrive(os.getcwd())[0], "\\download")
        cmd = [sys.executable, "-m", "yt_dlp", "-P", download_root, url]

        try:
            self.download_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )

            self.monitoring = True
            for line in iter(self.download_process.stdout.readline, ''):
                if not self.monitoring:
                    break

                # Parse progress info
                if '[download]' in line:
                    # Extract percentage, size, speed, ETA
                    self.root.after(0, self.log_message, line)

                    # Update status bar with summary
                    match = re.search(r'(\d+\.\d+)%.*?(\d+\.\d+\w+iB).*?(\d+\.\d+\w+iB/s)', line)
                    if match:
                        percent, size, speed = match.groups()
                        status = f"⬇ Downloading: {percent}% | Size: {size} | Speed: {speed}"
                        self.root.after(0, self.status_label.config, {'text': status})
                else:
                    self.root.after(0, self.log_message, line)

            self.download_process.wait()

            if self.download_process.returncode == 0:
                self.root.after(0, self.log_message, f"\n{'='*60}\n")
                self.root.after(0, self.log_message, "✅ Download completed successfully!\n")
                self.root.after(0, self.log_message, f"Location: {download_root}\n")
                self.root.after(0, self.log_message, f"{'='*60}\n")
                self.root.after(0, self.status_label.config, {'text': '✅ Download complete!'})
            else:
                self.root.after(0, self.log_message, "\n❌ Download failed.\n")
                self.root.after(0, self.status_label.config, {'text': '❌ Download failed'})

        except Exception as e:
            self.root.after(0, self.log_message, f"\n❌ Error: {e}\n")
            self.root.after(0, self.status_label.config, {'text': f'❌ Error: {e}'})

        finally:
            self.root.after(0, self.download_btn.config, {'state': tk.NORMAL})
            self.monitoring = False

def main():
    gartner_url = sys.argv[1] if len(sys.argv) > 1 else None

    root = tk.Tk()
    app = GartnerHelperGUI(root, gartner_url)
    root.mainloop()

if __name__ == "__main__":
    main()