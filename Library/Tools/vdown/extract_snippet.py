import re
import html

def extract_snippet():
    with open("page_source.html", "r", encoding="utf-8") as f:
        content = f.read()

    # Look for the pattern we saw: e&quot;:&quot;{\&quot;url\&quot;: \&quot;htt
    # It seems to be part of a JSON string.
    # We'll search for "url" followed by http, handling HTML entities

    # Simple regex for the encoded string
    # "url":"http...
    # encoded: &quot;url&quot;:&quot;http... or similar

    print("--- Hunting for encoded URLs ---")

    # Regex for HTML encoded JSON url
    # &quot;url&quot;:&quot;(http[^&]+)
    regex = r'&quot;url&quot;\s*:\s*&quot;(http[^&"]+)&quot;'

    matches = re.findall(regex, content)
    for m in matches:
        # Decode deeper if needed (e.g. escaped slashes)
        url = m.replace('\\/', '/')
        print(f"Found URL: {url}")

    # Also standard JSON
    regex_std = r'"url"\s*:\s*"(http[^"]+)"'
    matches_std = re.findall(regex_std, content)
    for m in matches_std:
       url = m.replace('\\/', '/')
       print(f"Found Standard URL: {url}")

if __name__ == "__main__":
    extract_snippet()