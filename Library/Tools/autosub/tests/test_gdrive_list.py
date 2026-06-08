import os
import sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive.file']
TOKEN_PATH = '/Users/shanfu/cc/.agents/skills/google-drive-sync/token.json'
PARENT_ID = '18iAFFSuHQmZlxVN0dri1Gbje9SmpS96f'

def test_list():
    if not os.path.exists(TOKEN_PATH):
        print("Token not found")
        return
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    service = build('drive', 'v3', credentials=creds)
    
    query = f"'{PARENT_ID}' in parents and trashed=false"
    try:
        results = service.files().list(
            q=query, spaces='drive',
            fields='nextPageToken, files(id, name, mimeType, size, modifiedTime)',
            pageSize=10
        ).execute()
        print("Success!")
        print(f"Found {len(results.get('files', []))} files")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_list()
