import sys
import os
import subprocess
import time
from playwright.sync_api import sync_playwright
import http.cookiejar

DOWNLOAD_ROOT = os.path.join(os.path.splitdrive(os.getcwd())[0], "\\download")

def log(msg):
    print(f"[Manual Assist] {msg}")

def capture_and_download(url):
    with sync_playwright() as p:
        log("Launching browser (Headful)...")
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()

        # Load cookies
        if os.path.exists("cookies.txt"):
            try:
                cj = http.cookiejar.MozillaCookieJar("cookies.txt")
                cj.load(ignore_discard=True, ignore_expires=True)
                pw_cookies = []
                for c in cj:
                     pw_cookies.append({'name': c.name, 'value': c.value, 'domain': c.domain, 'path': c.path, 'secure': c.secure})
                context.add_cookies(pw_cookies)
                log("Cookies injected.")
            except: pass

        page = context.new_page()

        found_urls = []
        def handle_request(request):
            u = request.url
            if ".m3u8" in u and "gartner" not in u:
                 found_urls.append(u)

        page.on("request", handle_request)

        log(f"Navigating to {url}")
        page.goto(url)

        print("\n" + "="*60)
        print("ACTION REQUIRED: The browser is now open.")
        print("1. Please interact with the page (click Play) to start the video.")
        print("2. Wait until the video starts playing.")
        print("3. Press ENTER in this terminal when you are ready.")
        print("="*60 + "\n")

        try:
            input("Press Enter to finish capture...")
        except EOFError:
            pass # Handle non-interactive case

        log(f"Captured {len(found_urls)} potential URLs.")

        browser.close()

        if found_urls:
            mux_url = found_urls[-1]
            log(f"Selected URL: {mux_url}")

            # Download
            if not os.path.exists(DOWNLOAD_ROOT): os.makedirs(DOWNLOAD_ROOT)
            cmd = [sys.executable, "-m", "yt_dlp", "-P", DOWNLOAD_ROOT, mux_url]
            subprocess.run(cmd)
        else:
            log("No URLs captured. Please try again.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python manual_assist.py <URL>")
    else:
        capture_and_download(sys.argv[1])