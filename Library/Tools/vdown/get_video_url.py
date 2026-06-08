import sys
import os
import http.cookiejar
from playwright.sync_api import sync_playwright
import time

def get_m3u8(url, cookies_path):
    # 1. Load Cookies
    cj = http.cookiejar.MozillaCookieJar(cookies_path)
    try:
        cj.load(ignore_discard=True, ignore_expires=True)
        print(f"Loaded {len(cj)} cookies from {cookies_path}")
    except Exception as e:
        print(f"Error loading cookies: {e}")
        return

    # Convert to Playwright format
    # Playwright wants: {name, value, domain, path, secure, httpOnly, sameSite, expires}
    # Simple conversion:
    playwright_cookies = []
    for c in cj:
        cookie_dict = {
            'name': c.name,
            'value': c.value,
            'domain': c.domain,
            'path': c.path,
            'secure': c.secure
        }
        # Handle expires if present
        if c.expires:
             cookie_dict['expires'] = c.expires

        playwright_cookies.append(cookie_dict)

    # 2. Launch Playwright
    with sync_playwright() as p:
        print("Launching browser (Headful)...")
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()

        # Add cookies
        try:
            context.add_cookies(playwright_cookies)
            print("Cookies injected.")
        except Exception as e:
            print(f"Warning: Failed to inject some cookies: {e}")

        page = context.new_page()

        # 3. Setup interception
        found_urls = set()
        log_file = open("network_log.txt", "w", encoding="utf-8")

        def handle_request(request):
            url_lower = request.url.lower()
            try:
                log_file.write(f"{request.method} {request.url}\n")
            except:
                pass

            if "master.m3u8" in url_lower:
                print(f"\n[!!!] Found master.m3u8: {request.url}")
                found_urls.add(request.url)
            elif ".m3u8" in url_lower:
                print(f"\n[!] Found .m3u8: {request.url}")
                found_urls.add(request.url)
            elif ".mp4" in url_lower:
                 print(f"\n[!] Found mp4: {request.url}")
                 found_urls.add(request.url)
            elif "manifest" in url_lower and "video" in request.resource_type:
                 print(f"\n[!] Found manifest: {request.url}")
                 found_urls.add(request.url)

        page.on("request", handle_request)

        print(f"Navigating to {url}...")
        try:
            page.goto(url, timeout=60000)
            print("Page loaded. Waiting for stability...")
            page.wait_for_timeout(5000)

            # Attempt to click play buttons
            print("Looking for play buttons...")
            # Generic play button selectors
            play_selectors = [
                "button[title='Play']",
                "button[aria-label='Play']",
                ".vjs-big-play-button",
                "div[class*='play']",
                "button[class*='play']"
            ]

            clicked = False
            for sel in play_selectors:
                if page.is_visible(sel):
                    print(f"Found potential play button: {sel}")
                    try:
                        page.click(sel, timeout=2000)
                        print("Clicked!")
                        clicked = True
                        page.wait_for_timeout(2000) # Wait for reaction
                    except:
                        print(f"Failed to click {sel}")

            # If no main page buttons, check iframes
            for frame in page.frames:
                if frame == page.main_frame: continue
                print(f"Checking frame: {frame.url}")
                for sel in play_selectors:
                    try:
                        if frame.is_visible(sel):
                             print(f"Found play button in frame {frame.url}: {sel}")
                             frame.click(sel, timeout=2000)
                             clicked = True
                    except:
                        pass

            print("Waiting for video traffic...")
            page.wait_for_timeout(15000)

            # Take screenshot for debugging
            page.screenshot(path="screenshot_debug.png")
            print("Screenshot saved to screenshot_debug.png")

        except Exception as e:
            print(f"Navigation/Interaction error: {e}")
            page.screenshot(path="error_screenshot.png")

        log_file.close()
        if found_urls:
            print("\n--- Summary of Found URLs ---")
            for u in found_urls:
                print(u)

            # Save cookies to file for yt-dlp
            print("Exporting cookies to cookies_final.txt...")
            try:
                cookies = context.cookies()
                with open("cookies_final.txt", "w") as f:
                    f.write("# Netscape HTTP Cookie File\n")
                    for c in cookies:
                        domain = c['domain']
                        flag = "TRUE" if domain.startswith('.') else "FALSE"
                        path = c['path']
                        secure = "TRUE" if c['secure'] else "FALSE"
                        expires = str(int(c['expires'])) if 'expires' in c else "0"
                        name = c['name']
                        value = c['value']
                        f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")
                print("Cookies exported.")
            except Exception as e:
                print(f"Error exporting cookies: {e}")

        else:
            print("\nNo video URLs found. Check network_log.txt")

        browser.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python get_video_url.py <URL>")
        sys.exit(1)

    url = sys.argv[1]
    cookies = "cookies.txt"
    get_m3u8(url, cookies)