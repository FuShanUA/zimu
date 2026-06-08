from playwright.sync_api import sync_playwright
import os
import sys

def main():
    target_url = "https://labs.google"
    screenshot_path = os.path.join(os.getcwd(), "google_labs.png")

    print(f"Connecting to Playwright to visit {target_url}...")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(target_url, wait_until="networkidle")
            print(f"Page title: {page.title()}")
            page.screenshot(path=screenshot_path)
            print(f"Screenshot saved to: {screenshot_path}")
            browser.close()
    except Exception as e:
        print(f"Error visiting site: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()