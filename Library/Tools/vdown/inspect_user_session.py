import requests
import http.cookiejar
import json
import os

def fetch_user_session():
    cookies_file = "cookies.txt"
    cj = http.cookiejar.MozillaCookieJar(cookies_file)
    try:
        if os.path.exists(cookies_file):
            cj.load(ignore_discard=True, ignore_expires=True)
            print("Cookies loaded.")
    except:
        pass

    session = requests.Session()
    session.cookies = cj
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json'
    })

    url = "https://api.bizzabo.com/api/v2/agenda/events/800562/userSessions"

    # Try POSTing empty JSON as seen in some Bizzabo implementations
    # Sometimes it needs {sessionId: ...}

    # First attempt: simple empty POST (often used to 'join' the event context)
    try:
        print(f"POSTing to {url}...")
        response = session.post(url, json={})
        print(f"Status: {response.status_code}")

        try:
            data = response.json()
            with open("user_session_response.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print("Saved response to user_session_response.json")
        except:
             print("Response not JSON:")
             print(response.text[:1000])

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_user_session()