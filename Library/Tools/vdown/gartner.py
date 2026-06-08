import requests
import http.cookiejar
import json
import re
import sys
import os
import subprocess
import datetime
import time

# --- Configuration ---
# Mirroring 'download.py' download root
DOWNLOAD_ROOT = os.path.join(os.path.splitdrive(os.getcwd())[0], "\\download")

def log(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def get_session_details_from_url(url):
    """
    Extracts eventId and sessionId from URL.
    Format: https://webinar.gartner.com/{eventId}/agenda/session/{sessionId}...
    """
    match = re.search(r'webinar\.gartner\.com/(\d+)/agenda/session/(\d+)', url)
    if match:
        return match.group(1), match.group(2)
    match = re.search(r'bizzabo\.com/(\d+)/agenda/session/(\d+)', url)
    if match:
        return match.group(1), match.group(2)
    return None, None

def fetch_mux_url(event_id, session_id, cookies_file="cookies.txt"):
    """
    Fetches the virtual session recording metadata from Bizzabo API.
    Returns the Mux playback URL if found.
    """
    cj = http.cookiejar.MozillaCookieJar(cookies_file)
    if os.path.exists(cookies_file):
        try:
            cj.load(ignore_discard=True, ignore_expires=True)
            log(f"Loaded {len(cj)} cookies from {cookies_file}")
        except Exception as e:
            log(f"Warning: Failed to load cookies: {e}")
            return None

    session = requests.Session()
    session.cookies = cj
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': f'https://webinar.gartner.com/{event_id}/agenda/session/{session_id}',
        'Origin': 'https://webinar.gartner.com',
        'x-bizzabo-user-agent': 'BizzaboWebAttendee/2.0.0'
    })

    api_url = f"https://api.bizzabo.com/api/v2/agenda/events/{event_id}/sessions/{session_id}/virtualSession/recording"

    log(f"Fetching recording metadata from: {api_url}")
    try:
        response = session.get(api_url)
        if response.status_code != 200:
            log(f"API Error: Status {response.status_code}")
            return None

        data = response.json()
        json_str = json.dumps(data)

        mux_matches = re.findall(r'https://stream\.mux\.com/[a-zA-Z0-9\-\_]+\.m3u8', json_str)
        if mux_matches: return mux_matches[0]

        pid_matches = re.findall(r'"playbackId"\s*:\s*"([a-zA-Z0-9\-\_]+)"', json_str)
        if pid_matches: return f"https://stream.mux.com/{pid_matches[0]}.m3u8"

        return None
    except Exception as e:
        log(f"Exception fetching API: {e}")
        return None

def fetch_from_active_browser():
    """
    Connects to user's existing Chrome browser via CDP and extracts m3u8 URL.
    User must start Chrome with: chrome.exe --remote-debugging-port=9222
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("Playwright not installed.")
        return None

    log("Attempting to connect to your active Chrome browser...")
    log("(Make sure Chrome was started with: chrome.exe --remote-debugging-port=9222)")

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            contexts = browser.contexts
            if not contexts:
                log("No browser contexts found. Make sure a Chrome window is open.")
                return None

            context = contexts[0]
            pages = context.pages
            if not pages:
                log("No pages found in browser.")
                return None

            # Find the Gartner page
            gartner_page = None
            for page in pages:
                if "gartner.com" in page.url or "bizzabo.com" in page.url:
                    gartner_page = page
                    break

            if not gartner_page:
                log("No Gartner/Bizzabo page found in open tabs.")
                return None

            log(f"Found page: {gartner_page.url}")

            # Listen for network requests
            found_urls = []
            def handle_request(request):
                u = request.url
                if ".m3u8" in u and "gartner" not in u:
                    found_urls.append(u)

            gartner_page.on("request", handle_request)

            log("Monitoring network traffic for 10 seconds...")
            log("(If video isn't playing, click Play now)")
            gartner_page.wait_for_timeout(10000)

            browser.close()

            if found_urls:
                return found_urls[-1]
            else:
                log("No .m3u8 URLs captured.")
                return None

    except Exception as e:
        log(f"CDP connection error: {e}")
        log("Make sure Chrome is running with: chrome.exe --remote-debugging-port=9222")
        return None

def download_stream(url):
    log(f"Starting download for: {url}")
    if not os.path.exists(DOWNLOAD_ROOT): os.makedirs(DOWNLOAD_ROOT)
    cmd = [sys.executable, "-m", "yt_dlp", "-P", DOWNLOAD_ROOT, url]
    try:
        subprocess.run(cmd, check=True)
        log("Download finished.")
    except subprocess.CalledProcessError as e:
        log(f"Download failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    page_url = sys.argv[1]
    event_id, session_id = get_session_details_from_url(page_url)
    if not event_id: sys.exit(1)

    mux_url = fetch_mux_url(event_id, session_id)

    if mux_url:
        download_stream(mux_url)
    else:
        log("Failed to extract video URL.")