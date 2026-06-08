import os
import sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive']
TOKEN_PATH = '/Users/shanfu/cc/.agents/skills/google-drive-sync/token.json'
PARENT_ID = '18iAFFSuHQmZlxVN0dri1Gbje9SmpS96f'

def search_lost_files():
    if not os.path.exists(TOKEN_PATH):
        print("Token not found")
        return
    
    # Try with both standard scopes as the token might contain either
    creds = Credentials.from_authorized_user_file(TOKEN_PATH)
    service = build('drive', 'v3', credentials=creds)
    
    # 1. Search inside the target Parent folder
    print(f"Searching inside parent folder {PARENT_ID}...")
    query = f"'{PARENT_ID}' in parents and name contains 'Sorkin' and trashed=false"
    try:
        results = service.files().list(
            q=query, spaces='drive',
            fields='files(id, name, mimeType, size, modifiedTime, parents)',
        ).execute()
        files = results.get('files', [])
        print(f"Found {len(files)} files/folders inside parent matching 'Sorkin':")
        for f in files:
            print(f" - {f['name']} (ID: {f['id']}, Type: {f['mimeType']})")
    except Exception as e:
        print(f"Error searching inside parent: {e}")
        
    # 2. Search globally in Drive for the video ID "jUK-VYCh5go"
    print("\nSearching globally in Drive for video ID 'jUK-VYCh5go'...")
    query_id = "name contains 'jUK-VYCh5go' and trashed=false"
    try:
        results = service.files().list(
            q=query_id, spaces='drive',
            fields='files(id, name, mimeType, size, modifiedTime, parents)',
        ).execute()
        files = results.get('files', [])
        print(f"Found {len(files)} files/folders globally matching 'jUK-VYCh5go':")
        for f in files:
            print(f" - {f['name']} (ID: {f['id']}, Type: {f['mimeType']}, Parents: {f.get('parents')})")
    except Exception as e:
        print(f"Error searching globally: {e}")

if __name__ == "__main__":
    search_lost_files()
