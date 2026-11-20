"""YouTube Data API v3 uploads (Shorts) with a hard safety default.

SAFETY RULES (do not weaken these):
1. DRY-RUN IS THE DEFAULT. With AUTO_UPLOAD=false, upload_clip()
   simulates the upload and logs it — it never touches the YouTube API.
2. A real upload needs BOTH AUTO_UPLOAD=true AND a valid OAuth token.
3. Quota guard: one upload costs 1600 of the 10,000 default daily
   units, so MAX_UPLOADS_PER_DAY defaults to 6 and is enforced per
   calendar day (UTC) against the uploads log.
4. Every attempt — simulated, blocked, succeeded, failed — is logged
   with its video id or error.

OAuth: google-auth-oauthlib Flow, client config from env vars
(YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET) or a client_secret.json
file. Tokens live in token.json (gitignored, never in code).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
UPLOAD_COST_UNITS = 1600
DEFAULT_DAILY_QUOTA = 10000


class UploadBlocked(Exception):
    """Raised when an upload is refused (quota, auth, or config)."""


class YouTubeUploader:
    def __init__(self, data_dir=None, auto_upload=False,
                 max_uploads_per_day=6,
                 client_id=None, client_secret=None,
                 client_secret_file=None, token_file=None):
        self.data_dir = Path(data_dir) if data_dir else Path("data")
        self.auto_upload = bool(auto_upload)
        self.max_uploads_per_day = int(max_uploads_per_day)
        self.client_id = client_id or os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
        self.client_secret = (client_secret
                              or os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip())
        self.client_secret_file = Path(
            client_secret_file or os.environ.get(
                "YOUTUBE_CLIENT_SECRET_FILE", "client_secret.json"))
        self.token_file = Path(
            token_file or os.environ.get(
                "YOUTUBE_TOKEN_FILE", self.data_dir / "token.json"))

    # -- configuration / auth state ----------------------------------------

    def client_config(self):
        """OAuth client config dict, from env vars or client_secret.json."""
        if self.client_id and self.client_secret:
            return {"web": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost:8000/auth/youtube/callback"],
            }}
        if self.client_secret_file.exists():
            return json.loads(self.client_secret_file.read_text())
        return None

    def is_configured(self) -> bool:
        return self.client_config() is not None

    def is_authorized(self) -> bool:
        """True when a token file exists and its credentials load."""
        if not self.token_file.exists():
            return False
        try:
            from google.oauth2.credentials import Credentials
            creds = Credentials.from_authorized_user_file(
                str(self.token_file), SCOPES)
            return creds is not None
        except Exception:
            return False

    def get_credentials(self):
        """Load + refresh OAuth credentials. Raises on failure."""
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_file(
            str(self.token_file), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.token_file.write_text(creds.to_json())
        if not creds.valid:
            raise UploadBlocked("Stored YouTube token is invalid — re-authorize "
                                "via /auth/youtube.")
        return creds

    def get_auth_url(self, redirect_uri):
        """Start the OAuth flow. Returns (authorization_url, state)."""
        from google_auth_oauthlib.flow import Flow

        config = self.client_config()
        if not config:
            raise UploadBlocked("YouTube OAuth is not configured: set "
                                "YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET or "
                                "provide client_secret.json.")
        flow = Flow.from_client_config(config, scopes=SCOPES,
                                       redirect_uri=redirect_uri)
        url, state = flow.authorization_url(
            access_type="offline", include_granted_scopes="true",
            prompt="consent")
        return url, state

    def exchange_code(self, code, state, redirect_uri):
        """Finish the OAuth flow: exchange code for tokens, save token.json."""
        from google_auth_oauthlib.flow import Flow

        config = self.client_config()
        flow = Flow.from_client_config(config, scopes=SCOPES, state=state,
                                       redirect_uri=redirect_uri)
        flow.fetch_token(code=code)
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(flow.credentials.to_json())
        return True

    def build_service(self):
        """YouTube API client. Only ever called for a real upload."""
        from googleapiclient.discovery import build

        return build("youtube", "v3", credentials=self.get_credentials())

    # -- quota --------------------------------------------------------------

    def uploads_today(self, db_path) -> int:
        from .app import store

        return store.uploads_today_count(db_path)

    def quota_used_units(self, db_path) -> int:
        return self.uploads_today(db_path) * UPLOAD_COST_UNITS

    def quota(self, db_path) -> dict:
        used = self.uploads_today(db_path)
        return {
            "uploads_today": used,
            "max_uploads_per_day": self.max_uploads_per_day,
            "quota_units_used": used * UPLOAD_COST_UNITS,
            "quota_units_daily": DEFAULT_DAILY_QUOTA,
            "uploads_remaining": max(0, self.max_uploads_per_day - used),
        }

    def can_upload(self, db_path) -> tuple:
        """(allowed, reason). Real uploads need auto_upload + auth + quota."""
        if not self.auto_upload:
            return False, "AUTO_UPLOAD is off (dry-run mode)"
        if not self.is_authorized():
            return False, "No YouTube OAuth token — visit /auth/youtube"
        if self.uploads_today(db_path) >= self.max_uploads_per_day:
            return False, (f"Daily upload limit reached "
                           f"({self.max_uploads_per_day}/day)")
        return True, "ok"

    # -- upload --------------------------------------------------------------

    def upload_clip(self, db_path, clip, file_path, title=None,
                    description=None, tags=None) -> dict:
        """Upload one clip as a Short, or simulate it in dry-run mode.

        clip: dict with at least {"id": ...}. Returns a result dict and
        always logs the attempt. In dry-run mode this NEVER calls the
        YouTube API (build_service is not even reached).
        """
        from .app import store

        clip_id = clip.get("id")
        title = (title or (clip.get("seo") or {}).get("titles", [""])[0]
                 or "GTA 6 Shorts")
        description = description or (clip.get("seo") or {}).get("description", "")
        tags = tags or (clip.get("seo") or {}).get("tags", [])

        if not self.auto_upload:
            result = {
                "dry_run": True,
                "status": "simulated",
                "title": title,
                "message": ("Dry-run: AUTO_UPLOAD is off — nothing was sent "
                            "to YouTube."),
            }
            store.log_upload(db_path, clip_id, status="simulated",
                             dry_run=1, error="", youtube_video_id="")
            return result

        allowed, reason = self.can_upload(db_path)
        if not allowed:
            store.log_upload(db_path, clip_id, status="blocked",
                             dry_run=0, error=reason, youtube_video_id="")
            raise UploadBlocked(reason)

        path = Path(file_path)
        if not path.exists():
            raise UploadBlocked(f"Clip file not found: {path}")

        try:
            youtube = self.build_service()
            body = {
                "snippet": {
                    "title": title[:100],
                    "description": description,
                    "tags": tags[:30],
                    "categoryId": "20",  # Gaming
                    "defaultLanguage": "en",
                },
                "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
            }
            from googleapiclient.http import MediaFileUpload
            media = MediaFileUpload(str(path), mimetype="video/mp4",
                                    chunksize=-1, resumable=True)
            request = youtube.videos().insert(
                part="snippet,status", body=body, media_body=media)
            response = None
            while response is None:
                _, response = request.next_chunk()
            video_id = response.get("id", "")
            store.log_upload(db_path, clip_id, status="uploaded",
                             dry_run=0, error="",
                             youtube_video_id=video_id)
            store.update_clip(db_path, clip_id, status="uploaded",
                              youtube_video_id=video_id)
            return {
                "dry_run": False,
                "status": "uploaded",
                "youtube_video_id": video_id,
                "url": f"https://www.youtube.com/shorts/{video_id}",
                "title": title,
            }
        except UploadBlocked:
            raise
        except Exception as exc:  # noqa: BLE001 - log + surface the real error
            err = str(exc)[:500]
            store.log_upload(db_path, clip_id, status="failed",
                             dry_run=0, error=err, youtube_video_id="")
            raise UploadBlocked(f"YouTube upload failed: {err}") from exc
