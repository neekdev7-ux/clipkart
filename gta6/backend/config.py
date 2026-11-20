"""Central configuration for ClipNova GTA 6 Edition.

Every setting comes from the environment with a safe default. The
safety-critical defaults: AUTO_UPLOAD is off (dry-run), the monitor
does not start on boot, and no credentials are ever hardcoded.
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {
        "1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


DEFAULT_QUERIES = [
    "GTA 6 live",
    "GTA VI live",
    "GTA 6 gameplay",
    "GTA 6 trailer",
    "GTA 6 leak",
    "GTA 6 Vice City",
    "GTA 6 news",
]


def get_queries() -> list:
    raw = os.environ.get("GTA6_QUERIES", "").strip()
    if not raw:
        return list(DEFAULT_QUERIES)
    return [q.strip() for q in raw.split(",") if q.strip()]


class Settings:
    """Read-once settings object. Tests can build one with overrides."""

    def __init__(self, **overrides):
        self.data_dir = Path(overrides.get(
            "data_dir", os.environ.get("CLIPNOVA_DATA", PROJECT_ROOT / "data")))
        self.db_path = self.data_dir / "clipnova.db"
        self.job_root = self.data_dir / "jobs"
        self.stream_root = self.data_dir / "streams"
        self.clip_root = self.data_dir / "clips"
        self.token_path = Path(overrides.get(
            "token_path", os.environ.get(
                "YOUTUBE_TOKEN_FILE", self.data_dir / "token.json")))
        self.client_secret_path = Path(overrides.get(
            "client_secret_path", os.environ.get(
                "YOUTUBE_CLIENT_SECRET_FILE",
                PROJECT_ROOT / "client_secret.json")))

        self.whisper_model = overrides.get(
            "whisper_model", os.environ.get("WHISPER_MODEL", "base"))
        self.max_jobs_per_hour = overrides.get(
            "max_jobs_per_hour", _env_int("MAX_JOBS_PER_HOUR", 3))

        # YouTube API / OAuth (all optional until upload is wanted).
        self.youtube_api_key = overrides.get(
            "youtube_api_key", os.environ.get("YOUTUBE_API_KEY", "").strip())
        self.youtube_client_id = overrides.get(
            "youtube_client_id", os.environ.get("YOUTUBE_CLIENT_ID", "").strip())
        self.youtube_client_secret = overrides.get(
            "youtube_client_secret",
            os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip())

        # Upload safety: dry-run is the default. Real uploads only when
        # AUTO_UPLOAD=true AND a valid OAuth token exists.
        self.auto_upload = overrides.get(
            "auto_upload", _env_bool("AUTO_UPLOAD", False))
        self.max_uploads_per_day = overrides.get(
            "max_uploads_per_day", _env_int("MAX_UPLOADS_PER_DAY", 6))
        # One videos.insert upload costs 1600 quota units; the default
        # YouTube Data API daily quota is 10,000 units.
        self.upload_cost_units = 1600
        self.daily_quota_units = 10000

        # Monitor / streams.
        self.monitor_on_start = overrides.get(
            "monitor_on_start", _env_bool("MONITOR_ON_START", False))
        self.queries = overrides.get("queries", get_queries())
        self.min_viewers = overrides.get(
            "min_viewers", _env_int("MIN_VIEWERS", 10))
        self.max_watched_streams = overrides.get(
            "max_watched_streams", _env_int("MAX_WATCHED_STREAMS", 3))
        self.discovery_interval_seconds = overrides.get(
            "discovery_interval_seconds",
            _env_int("DISCOVERY_INTERVAL_SECONDS", 120))
        self.segment_minutes = overrides.get(
            "segment_minutes", _env_int("SEGMENT_MINUTES", 5))
        self.retention_hours = overrides.get(
            "retention_hours", _env_float("RETENTION_HOURS", 2.0))
        self.disk_cap_gb = overrides.get(
            "disk_cap_gb", _env_float("DISK_CAP_GB", 20.0))
        self.clip_min_score = overrides.get(
            "clip_min_score", _env_int("CLIP_MIN_SCORE", 60))
        self.max_clips_per_segment = overrides.get(
            "max_clips_per_segment", _env_int("MAX_CLIPS_PER_SEGMENT", 2))
        self.clip_seconds = overrides.get(
            "clip_seconds", _env_int("CLIP_SECONDS", 45))

        for p in (overrides.get(k, getattr(self, k))
                  for k in ("data_dir", "job_root", "stream_root", "clip_root")):
            Path(p).mkdir(parents=True, exist_ok=True)


settings = Settings()
