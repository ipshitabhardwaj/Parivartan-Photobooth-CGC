"""
One-time Google Drive setup for the kiosk.  Run:   python setup_drive.py

Before you run it you need credentials.json (an OAuth "Desktop app" client) in this folder; the README has the
step-by-step. This script then:
  1. opens your browser so you can sign in with the Google account that should own the photos and click Allow
  2. saves token.json (the kiosk uses it from now on, no browser needed)
  3. creates the Drive folder "CGC SQUARE Photos" and turns on "anyone with the link can view"
  4. uploads and deletes a tiny test file to prove uploading works
  5. prints the folder link (that is what the QR code on the kiosk points to)
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main():
    import drive_storage as ds

    if not ds.HAVE_GOOGLE:
        print("The Google libraries are missing. Run:  pip install -r requirements.txt")
        return 1
    if not os.path.exists(ds.CREDENTIALS_FILE):
        print(f"credentials.json was not found in {HERE}")
        print("Create an OAuth client of type 'Desktop app' in Google Cloud Console, download its JSON and save it here")
        print("as credentials.json (see 'Google Drive setup' in the README).")
        return 1

    if os.path.exists(ds.TOKEN_FILE):
        os.remove(ds.TOKEN_FILE)                      # always start a fresh sign-in
    print("Opening your browser. Sign in with the Google account that will own the photos, then click Allow...")
    try:
        creds = ds.load_credentials(interactive=True)
        service = ds.build_service(creds)
        folder_id = ds.ensure_folder(service)
    except Exception as exc:
        print(f"\nSetup failed: {exc}")
        print("Common causes: the Drive API is not enabled in your Google Cloud project, or your Google account is not")
        print("listed as a Test user on the OAuth consent screen (see the README).")
        return 1

    print("Testing an upload...")
    try:
        from googleapiclient.http import MediaIoBaseUpload
        media = MediaIoBaseUpload(io.BytesIO(b"kiosk setup test"), mimetype="text/plain")
        test = service.files().create(body={"name": "_setup_test.txt", "parents": [folder_id]}, media_body=media,
                                      fields="id").execute()
        service.files().delete(fileId=test["id"]).execute()
    except Exception as exc:
        print(f"Upload test failed: {exc}")
        return 1

    print("\nAll set.")
    print(f"  Drive folder: https://drive.google.com/drive/folders/{folder_id}")
    print("  Anyone with that link can view the photos. The QR code on the kiosk points to it.")
    print("  Photos will be saved on this computer in:", ds.PHOTO_DIR)
    print("  Keep token.json and credentials.json private. Start the kiosk with:  python server.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
