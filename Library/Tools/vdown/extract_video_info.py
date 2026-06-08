import re

def extract_info(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Regex patterns for Brightcove
        patterns = {
            "Brightcove Account": [r'data-account="(\d+)"', r'accountId:\s*"(\d+)"', r'playerKey:\s*"([^"]+)"'],
            "Brightcove Video ID": [r'data-video-id="(\d+)"', r'videoId:\s*"(\d+)"', r'videoId\s*=\s*"(\d+)"'],
            "M3U8 Link": [r'https?://[^\s"\'<>]+?\.m3u8'],
            "MP4 Link": [r'https?://[^\s"\'<>]+?\.mp4'],
            "Player ID": [r'data-player="([^"]+)"', r'playerId:\s*"([^"]+)"'],
            "Policy Key": [r'policyKey\s*:\s*"([^"]+)"', r'policyKey\s*=\s*"([^"]+)"'],
            "Bizzabo": [r'bizzabo'],
        }

        print(f"--- Scanning {file_path} ---")
        # Don't set found_any for Bizzabo, detecting it is just metadata
        found_video_id = False

        for label, regex_list in patterns.items():
            for pattern in regex_list:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    print(f"Found {label}: {matches[0]}")
                    if label != "Bizzabo":
                        found_video_id = True

                    unique_matches = set(matches)
                    if len(unique_matches) > 1:
                        print(f"  All unique matches: {unique_matches}")
                    break

        # Always search for context keywords to help debugging
        keywords = ['m3u8', 'mp4', 'broadcast', 'stream', 'master.m3u8', 'manifest']
        print("\n--- Context Search ---")
        for kw in keywords:
            if kw in content.lower():
                 print(f"\nContext for '{kw}':")
                 literals = [m.start() for m in re.finditer(re.escape(kw), content, re.IGNORECASE)]
                 for start in literals[:3]:
                     print(content[max(0, start-100):min(len(content), start+200)])
                     print("-" * 20)



    except Exception as e:
        print(f"Error reading file: {e}")

if __name__ == "__main__":
    extract_info("page_source.html")