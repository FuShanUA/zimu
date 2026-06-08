import requests
import http.cookiejar
import sys

def inspect_page(url, cookies_file):
    # Load cookies
    cj = http.cookiejar.MozillaCookieJar(cookies_file)
    try:
        cj.load(ignore_discard=True, ignore_expires=True)
        print(f"Loaded {len(cj)} cookies from {cookies_file}")
    except Exception as e:
        print(f"Error loading cookies: {e}")
        return

    # Create session
    session = requests.Session()
    session.cookies = cj
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })

    try:
        response = session.get(url)
        response.raise_for_status()
        print(f"Successfully fetched {url} (Status: {response.status_code})")

        # Save content to file for inspection
        with open("page_source.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        print("Saved page source to page_source.html")

        # Quick search for keywords
        keywords = ["m3u8", "mp4", "iframe", "embed", "video", "bizzabo", "jwplayer", "brightcove"]
        print("\n--- Key Findings ---")
        found = False
        for kw in keywords:
            if kw in response.text.lower():
                print(f"Found keyword '{kw}':")
                # Print context (naive implementation)
                lines = response.text.splitlines()
                for i, line in enumerate(lines):
                    if kw in line.lower():
                        print(f"  Line {i+1}: {line.strip()[:200]}...")
                        found = True
                        if found and i > 5: break # Limit output
                print("-" * 20)

        if not found:
            print("No obvious video keywords found.")

    except Exception as e:
        print(f"Error fetching page: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python inspect_page.py <URL>")
        sys.exit(1)

    url = sys.argv[1]
    cookies_path = "cookies.txt"
    inspect_page(url, cookies_path)