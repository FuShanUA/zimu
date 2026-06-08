import os
import sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive.file']
TOKEN_PATH = '/Users/shanfu/cc/.agents/skills/google-drive-sync/token.json'

def test_list():
    if not os.path.exists(TOKEN_PATH):
        print("Token not found")
        return
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    service = build('drive', 'v3', credentials=creds)
    
    try:
        print("Fetching root files...")
        results = service.files().list(
            pageSize=5,
            fields="nextPageToken, files(id, name)"
        ).execute()
        print("Success!")
        for f in results.get('files', []):
            print(f"File: {f['name']} ({f['id']})")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_list()
