from playwright.sync_api import sync_playwright
import os

print(f"HOME: {os.environ.get('HOME')}")
print(f"USERPROFILE: {os.environ.get('USERPROFILE')}")

try:
    with sync_playwright() as p:
        print("Launching browser...")
        browser = p.chromium.launch(headless=True)
        print("Browser launched successfully!")
        browser.close()
except Exception as e:
    print(f"Error: {e}")