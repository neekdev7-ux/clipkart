"""YouTube download + metadata via yt-dlp (imported lazily so the rest
of the app and the test suite work without it installed).
"""
from __future__ import annotations

import re
from pathlib import Path

YOUTUBE_RE = re.compile(
    r"^https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?|shorts/|live/|embed/|v/)|youtu\.be/)"
)


def is_youtube_url(url: str) -> bool:
    return bool(url and YOUTUBE_RE.match(url.strip()))


def _ydl_opts(extra=None):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": ("bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
                   "best[height<=1080][ext=mp4]/best[height<=1080]/best"),
        "merge_output_format": "mp4",
    }
    if extra:
        opts.update(extra)
    return opts


def get_video_info(url: str) -> dict:
    """Fetch title/thumbnail/duration without downloading."""
    import yt_dlp
    with yt_dlp.YoutubeDL(_ydl_opts()) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "video_id": info.get("id", ""),
        "title": info.get("title", "") or "",
        "thumbnail": info.get("thumbnail", "") or "",
        "duration": int(info.get("duration") or 0),
        "uploader": info.get("uploader", "") or "",
    }


def download_video(url: str, out_path) -> Path:
    """Download best mp4 <=1080p to out_path. Returns the final path."""
    import yt_dlp
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    opts = _ydl_opts({"outtmpl": str(out_path.with_suffix(""))})
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    # yt-dlp appends the real extension; resolve it.
    if out_path.exists():
        return out_path
    for candidate in out_path.parent.glob(out_path.stem + ".*"):
        if candidate.suffix.lower() in {".mp4", ".mkv", ".webm"}:
            return candidate
    raise FileNotFoundError(f"yt-dlp did not produce a file for {url}")
