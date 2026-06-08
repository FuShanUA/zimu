---
name: vdown
description: Download videos from YouTube, X.com, Vimeo, and Gartner webinars using yt-dlp with automatic cookie handling.
---

# Video Downloader Skill (vdown)

This skill downloads videos from various platforms using `yt-dlp` with intelligent source-specific handling.

## Usage

```
/vdown [URL] [optional_cookies_file]
```

## Recommended Method (GUI)

The `/vdown` command and backend scripts now support a graphical progress window by default when invoked via the wrapper.

### Commands

**GUI (Preferred)**
```powershell
python /Users/shanfu/cc/Library/Tools/vdown/vdown_gui.py "<URL>" " " "/Users/shanfu/cc/download"
```

**CLI (Backend)**
```powershell
python /Users/shanfu/cc/Library/Tools/vdown/download.py "<URL>" " " "/Users/shanfu/cc/download"
```

### Standard Platforms (Full Automation)
- **YouTube, X.com, Vimeo**: Fully automated download
- **Bilibili**: Automated download (may require cookies, see Troubleshooting)
- **Direct streams** (`.m3u8`, `.mp4`): Instant download, no extraction needed

### Gartner Webinars (Semi-Automated)
Gartner has bot detection that blocks full automation. Two methods available:

**Method 1: CDP Browser Control (Recommended)**
1. Start Chrome with debugging: `chrome.exe --remote-debugging-port=9222`
2. Open the Gartner webinar and play the video
3. Run: `python -c "import gartner; print(gartner.fetch_from_active_browser())"`
4. Copy the URL and run: `python download.py "<url>"`

**Method 2: Manual DevTools Extraction**
1. Open webinar in browser, press F12
2. Go to Network tab, filter by `m3u8`
3. Play the video
4. Copy the `.m3u8` URL that appears
5. Run: `python download.py "<url>"`

## Technical Details

- Downloads saved to `\download` on current drive (e.g., `D:\download`)
- Requires `yt-dlp` installed via pip
- **Windows Limitation**: Chrome's DPAPI encryption prevents automatic cookie extraction
- Smart URL detection skips unnecessary extraction for direct streams

## How Online YouTube Downloaders Work (vs. Windows Clients)

Online YouTube downloaders (like yt1z.click) can automatically handle authentication because:
1. They run on **Linux servers** where Chrome's DPAPI encryption doesn't apply
2. They extract cookies from server-side browser instances
3. They use these cookies to authenticate and download streams

**Why vdown can't do the same on Windows:**
- Chrome on Windows uses DPAPI (Data Protection API) to encrypt cookies
- `yt-dlp`'s `--cookies-from-browser chrome` fails with "Failed to decrypt with DPAPI"
- This is a Windows-specific security feature that can't be bypassed
- Manual cookie export is the only reliable method on Windows

## Authentication for Restricted Videos

For age-restricted, private, or "Sign in to confirm you're not a bot" videos:

### Step-by-Step Cookie Export (Windows)

1. **Install Extension**: Add "Get cookies.txt LOCALLY" from Chrome Web Store
2. **Open Incognito**: Open a new incognito/private window
3. **Navigate**: Go to `https://www.youtube.com/robots.txt` in the incognito tab
4. **Login**: Log into your YouTube account in that same incognito tab
5. **Export**: Click the extension icon → Export → Save to `/Users/shanfu/cc/vdown/cookies.txt`
6. **Close**: Close the incognito window immediately (prevents cookie rotation)
7. **Run**: Execute `/vdown <URL>` - it will automatically use cookies.txt

**Why incognito + robots.txt?**
- Incognito prevents cookie rotation/invalidation
- robots.txt ensures you're on youtube.com domain
- Closing immediately after export keeps cookies fresh

## Troubleshooting

**"Sign in to confirm you're not a bot" Error**: 
- This requires authentication - follow the cookie export steps above
- vdown will automatically detect and use cookies.txt

**"Failed to decrypt with DPAPI" Error**:
- This is expected on Windows - automatic cookie extraction doesn't work
- Use the manual cookie export method above

**Cookies Not Working**:
- Make sure you exported from an incognito window
- Ensure you visited robots.txt before exporting
- Close the incognito window immediately after export
- Try exporting fresh cookies

**Bilibili HTTP Error 412: Precondition Failed**:
- This is an anti-bot measure. It requires valid cookies.
- Export cookies from a logged-in Bilibili session (Incognito recommended).
- Save as `cookies.txt` or `bili_cookies.txt` in the skill directory.
- `vdown` will automatically detect and use these.

**WeChat / Other Platforms**:
- If a platform requires cookies, export them to a file (e.g., `weixin_cookies.txt`).
- Run using the optional argument: `/vdown [URL] weixin_cookies.txt`.

**Gartner API 403**: Normal behavior - use one of the semi-automated methods above

**Browser Environment Error** ($HOME not set): Run this once in PowerShell:
```powershell
[System.Environment]::SetEnvironmentVariable('HOME', $env:USERPROFILE, [System.EnvironmentVariableTarget]::User)
```