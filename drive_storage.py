"""
Numbered photo saving + Google Drive folder sync + the QR code for the folder.

Every photo is saved on this computer as photos/1.png, photos/2.png, photos/3.png ... (the numbering carries on
after a restart) and uploaded to ONE Google Drive folder under the same name. The QR code on the kiosk screen links to
that folder, so a student scans it and finds their photo by its number.

Credentials: OAuth for a normal Google account (a "Desktop app" client in credentials.json, signed in once with
`python setup_drive.py`, which saves token.json). Service accounts can't be used: they have no Drive storage of their
own, so uploads to a normal Drive fail. The app creates and shares its own folder, so the narrow `drive.file`
permission is enough (it can only touch what the app created).

Uploads happen in a background thread and are retried, so a Wi-Fi drop never loses or blocks a photo: the file is
already saved locally, and anything missing from Drive is uploaded when the connection returns (also after a restart).

Environment variables (all optional):
  PHOTO_DIR          where photos are saved, default ./photos
  GDRIVE_FOLDER_NAME name of the Drive folder the app creates, default "CGC SQUARE Photos"
  GDRIVE_FOLDER_ID   use an existing folder instead (needs the full `drive` permission; re-run setup_drive.py)
"""
import base64
import io
import json
import os
import queue
import re
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PHOTO_DIR = os.environ.get("PHOTO_DIR", os.path.join(HERE, "photos"))
CREDENTIALS_FILE = os.path.join(HERE, "credentials.json")
TOKEN_FILE = os.path.join(HERE, "token.json")
FOLDER_FILE = os.path.join(HERE, "drive_folder.json")
FOLDER_NAME = os.environ.get("GDRIVE_FOLDER_NAME", "CGC SQUARE Photos")
FOLDER_ID_ENV = os.environ.get("GDRIVE_FOLDER_ID", "").strip()
SCOPES = ["https://www.googleapis.com/auth/drive"] if FOLDER_ID_ENV else ["https://www.googleapis.com/auth/drive.file"]

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    HAVE_GOOGLE = True
except ImportError:
    HAVE_GOOGLE = False

try:
    import segno
    HAVE_SEGNO = True
except ImportError:
    HAVE_SEGNO = False

_NUMBERED = re.compile(r"^(\d+)\.png$")
_number_lock = threading.Lock()


# ---------------------------------------------------------------------------------------------------------------------
# Authorisation and folder (also used by setup_drive.py)
# ---------------------------------------------------------------------------------------------------------------------
def load_credentials(interactive=False):
    """Valid Google credentials from token.json (refreshing if needed). interactive=True opens the browser sign-in."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif interactive:
        if not os.path.exists(CREDENTIALS_FILE):
            raise RuntimeError("credentials.json is missing (see the Google Drive setup in the README)")
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0, prompt="consent")
    else:
        raise RuntimeError("Google Drive is not signed in: run  python setup_drive.py")
    with open(TOKEN_FILE, "w", encoding="utf-8") as fh:
        fh.write(creds.to_json())
    return creds


def build_service(creds):
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def ensure_folder(service):
    """Find or create the photo folder and make sure anyone with the link can view it. Returns its id."""
    folder_id = FOLDER_ID_ENV
    if not folder_id and os.path.exists(FOLDER_FILE):
        try:
            folder_id = json.load(open(FOLDER_FILE, encoding="utf-8")).get("id", "")
        except (OSError, ValueError):
            folder_id = ""
    if folder_id:
        try:
            info = service.files().get(fileId=folder_id, fields="id,trashed").execute()
            if info.get("trashed"):
                folder_id = ""
        except Exception:
            folder_id = ""                        # deleted, or not ours: make a fresh one
    if not folder_id:
        folder = service.files().create(
            body={"name": FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"}, fields="id").execute()
        folder_id = folder["id"]
        with open(FOLDER_FILE, "w", encoding="utf-8") as fh:
            json.dump({"id": folder_id, "name": FOLDER_NAME}, fh)
    perms = service.permissions().list(fileId=folder_id, fields="permissions(type,role)").execute().get("permissions", [])
    if not any(p.get("type") == "anyone" for p in perms):
        service.permissions().create(fileId=folder_id, body={"type": "anyone", "role": "reader"}).execute()
    return folder_id


def list_numbers(service, folder_id):
    """Numbers already in the Drive folder (from files called <number>.png)."""
    found, token = set(), None
    while True:
        res = service.files().list(q=f"'{folder_id}' in parents and trashed=false", fields="nextPageToken, files(name)",
                                   pageSize=1000, pageToken=token).execute()
        for f in res.get("files", []):
            m = _NUMBERED.match(f.get("name", ""))
            if m:
                found.add(int(m.group(1)))
        token = res.get("nextPageToken")
        if not token:
            return found


# ---------------------------------------------------------------------------------------------------------------------
# Background uploader
# ---------------------------------------------------------------------------------------------------------------------
class DriveSync:
    def __init__(self):
        self.folder_id = None
        self.floor = 0                    # highest number already in the Drive folder
        self.error = ""
        self._queue = queue.Queue()
        self._thread = None
        self._service = None

    def start(self):
        if self._thread:
            return
        if not HAVE_GOOGLE:
            self.error = "Google libraries are not installed (pip install -r requirements.txt)"
        elif not os.path.exists(TOKEN_FILE):
            self.error = "Google Drive is not set up yet: run  python setup_drive.py"
        else:
            self._thread = threading.Thread(target=self._run, name="drive-sync", daemon=True)
            self._thread.start()
        if self.error:
            print(f"[Drive] off: {self.error}. Photos are still saved in {PHOTO_DIR}")

    def enqueue(self, number, path):
        if self._thread:
            self._queue.put((number, path))

    def folder_url(self):
        return f"https://drive.google.com/drive/folders/{self.folder_id}" if self.folder_id else None

    def pending(self):
        return self._queue.qsize()

    # -- worker ---------------------------------------------------------------------------------------------------
    def _connect(self):
        service = build_service(load_credentials())
        folder_id = ensure_folder(service)
        in_drive = list_numbers(service, folder_id)
        self._service, self.folder_id = service, folder_id
        self.floor = max(in_drive, default=0)
        self.error = ""
        backlog = sorted(n for n, _ in _local_photos() if n not in in_drive)
        for n in backlog:
            self._queue.put((n, os.path.join(PHOTO_DIR, f"{n}.png")))
        print(f"[Drive] connected. Folder: {self.folder_url()}  ({len(backlog)} photo(s) waiting to upload)")

    def _upload(self, number, path):
        with open(path, "rb") as fh:
            data = fh.read()
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype="image/png", resumable=False)
        self._service.files().create(body={"name": f"{number}.png", "parents": [self.folder_id]},
                                     media_body=media, fields="id").execute()

    def _run(self):
        delay = 5
        while True:
            try:
                if self._service is None:
                    self._connect()
                number, path = self._queue.get()
                try:
                    self._upload(number, path)
                    print(f"[Drive] uploaded {number}.png")
                    delay = 5
                except Exception:
                    self._queue.put((number, path))          # keep it for the next try
                    raise
            except Exception as exc:
                self.error = str(exc)[:200]
                print(f"[Drive] problem: {self.error}. Retrying in {delay}s")
                if self._service is not None and "invalid_grant" in str(exc):
                    self._service = None                     # sign-in expired: needs python setup_drive.py
                time.sleep(delay)
                delay = min(60, delay * 2)


DRIVE = DriveSync()


# ---------------------------------------------------------------------------------------------------------------------
# Local numbered photos
# ---------------------------------------------------------------------------------------------------------------------
def _local_photos():
    if not os.path.isdir(PHOTO_DIR):
        return []
    out = []
    for name in os.listdir(PHOTO_DIR):
        m = _NUMBERED.match(name)
        if m:
            out.append((int(m.group(1)), name))
    return sorted(out)


def save_photo(png_bytes):
    """Save as the next number (1, 2, 3, ...) and queue the Google Drive upload. Returns (number, path)."""
    with _number_lock:
        os.makedirs(PHOTO_DIR, exist_ok=True)
        local_max = max((n for n, _ in _local_photos()), default=0)
        number = max(local_max, DRIVE.floor) + 1           # never reuse a number that is already in the Drive folder
        path = os.path.join(PHOTO_DIR, f"{number}.png")
        tmp = path + ".part"
        with open(tmp, "wb") as fh:
            fh.write(png_bytes)
        os.replace(tmp, path)
        DRIVE.floor = max(DRIVE.floor, number)
    DRIVE.enqueue(number, path)
    return number, path


def decode_png_data_url(data_url):
    """Bytes of a data:image/png;base64,... URL, or None if it isn't a PNG."""
    if not isinstance(data_url, str) or not data_url.startswith("data:image/png;base64,"):
        return None
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1], validate=True)
    except (ValueError, TypeError):
        return None
    return raw if raw.startswith(b"\x89PNG\r\n\x1a\n") else None


# ---------------------------------------------------------------------------------------------------------------------
# QR code for the Drive folder
# ---------------------------------------------------------------------------------------------------------------------
_qr_cache = {"url": None, "svg": None}


def qr_svg():
    """SVG bytes of a QR code for the Drive folder link, or None until Drive is connected."""
    url = DRIVE.folder_url()
    if not url or not HAVE_SEGNO:
        return None
    if _qr_cache["url"] != url:
        buf = io.BytesIO()
        segno.make(url, error="m").save(buf, kind="svg", scale=8, border=3, dark="#1d1530", light="#ffffff",
                                        xmldecl=False, svgns=True)
        _qr_cache.update(url=url, svg=buf.getvalue())
    return _qr_cache["svg"]
