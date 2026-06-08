import requests
import http.cookiejar
import json
import sys
import os

def fetch_session_data(url):
    cookies_file = "cookies.txt"
    cj = http.cookiejar.MozillaCookieJar(cookies_file)
    try:
        if os.path.exists(cookies_file):
            cj.load(ignore_discard=True, ignore_expires=True)
            print("Cookies loaded.")
        else:
            print("No cookies.txt found.")
    except Exception as e:
        print(f"Cookie load error: {e}")

    session = requests.Session()
    session.cookies = cj
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*'
    })

    try:
        print(f"Fetching {url}...")
        response = session.get(url)
        print(f"Status: {response.status_code}")

        try:
            data = response.json()
            with open("api_response.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print("Saved JSON to api_response.json")
        except:
            print("Response is not JSON. Saving text.")
            with open("api_response.txt", "w", encoding="utf-8") as f:
                f.write(response.text)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    url = "https://webinar.gartner.com/agenda/events/800562/sessions/1799544"
    fetch_session_data(url)