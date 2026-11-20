"""SQLite job store (stdlib sqlite3, one lock, thread-safe for the
BackgroundTasks worker + API threads)."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

_lock = threading.Lock()


def init_db(db_path) -> Path:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _lock, sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                title TEXT DEFAULT '',
                thumbnail TEXT DEFAULT '',
                duration REAL DEFAULT 0,
                status TEXT DEFAULT 'queued',
                progress INTEGER DEFAULT 0,
                message TEXT DEFAULT '',
                max_clips INTEGER DEFAULT 5,
                clip_seconds INTEGER DEFAULT 45,
                clips_json TEXT DEFAULT '[]',
                error TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # GTA 6 Edition: watched live streams.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS streams (
                id TEXT PRIMARY KEY,
                video_id TEXT UNIQUE NOT NULL,
                url TEXT NOT NULL,
                title TEXT DEFAULT '',
                channel TEXT DEFAULT '',
                viewers INTEGER DEFAULT 0,
                status TEXT DEFAULT 'watching',
                segments_dir TEXT DEFAULT '',
                error TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                last_seen TEXT DEFAULT (datetime('now'))
            )
        """)
        # GTA 6 Edition: detected clips from stream segments.
        # status: detected | approved | rejected | uploaded
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gta6_clips (
                id TEXT PRIMARY KEY,
                stream_id TEXT DEFAULT '',
                stream_title TEXT DEFAULT '',
                stream_url TEXT DEFAULT '',
                channel TEXT DEFAULT '',
                segment_file TEXT DEFAULT '',
                start REAL DEFAULT 0,
                end REAL DEFAULT 0,
                duration REAL DEFAULT 0,
                score REAL DEFAULT 0,
                reason TEXT DEFAULT '',
                text TEXT DEFAULT '',
                seo_json TEXT DEFAULT '{}',
                file_path TEXT DEFAULT '',
                status TEXT DEFAULT 'detected',
                youtube_video_id TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # GTA 6 Edition: every upload attempt (real, simulated, blocked,
        # failed) is logged here. Quota counts only real uploads.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clip_id TEXT DEFAULT '',
                youtube_video_id TEXT DEFAULT '',
                status TEXT DEFAULT '',
                dry_run INTEGER DEFAULT 1,
                error TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
    return db_path


def _connect(db_path):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def create_job(db_path, job_id, url, max_clips, clip_seconds):
    with _lock, _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO jobs (id, url, max_clips, clip_seconds) VALUES (?,?,?,?)",
            (job_id, url, max_clips, clip_seconds))


def update_job(db_path, job_id, **fields):
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    with _lock, _connect(db_path) as conn:
        conn.execute(f"UPDATE jobs SET {sets} WHERE id=?",
                     (*fields.values(), job_id))


def get_job(db_path, job_id):
    with _lock, _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        return None
    job = dict(row)
    try:
        job["clips"] = json.loads(job.pop("clips_json") or "[]")
    except json.JSONDecodeError:
        job["clips"] = []
    return job


def set_clips(db_path, job_id, clips):
    update_job(db_path, job_id, clips_json=json.dumps(clips))


# ---------------------------------------------------------------------------
# GTA 6 Edition: streams, clips, uploads
# ---------------------------------------------------------------------------

def _row_to_clip(row):
    clip = dict(row)
    try:
        clip["seo"] = json.loads(clip.pop("seo_json") or "{}")
    except json.JSONDecodeError:
        clip["seo"] = {}
    return clip


def create_stream(db_path, stream_id, video_id, url, title="", channel="",
                  viewers=0, segments_dir=""):
    with _lock, _connect(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO streams "
            "(id, video_id, url, title, channel, viewers, segments_dir) "
            "VALUES (?,?,?,?,?,?,?)",
            (stream_id, video_id, url, title, channel, viewers, segments_dir))


def get_stream(db_path, stream_id):
    with _lock, _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM streams WHERE id=?",
                           (stream_id,)).fetchone()
    return dict(row) if row else None


def get_stream_by_video_id(db_path, video_id):
    with _lock, _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM streams WHERE video_id=?",
                           (video_id,)).fetchone()
    return dict(row) if row else None


def list_streams(db_path, status=None):
    with _lock, _connect(db_path) as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM streams WHERE status=? ORDER BY last_seen DESC",
                (status,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM streams ORDER BY last_seen DESC").fetchall()
    return [dict(r) for r in rows]


def update_stream(db_path, stream_id, **fields):
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    with _lock, _connect(db_path) as conn:
        conn.execute(f"UPDATE streams SET {sets} WHERE id=?",
                     (*fields.values(), stream_id))


def delete_stream(db_path, stream_id):
    with _lock, _connect(db_path) as conn:
        conn.execute("DELETE FROM streams WHERE id=?", (stream_id,))


def create_clip(db_path, clip_id, **fields):
    fields = dict(fields)
    seo = fields.pop("seo", {})
    fields["seo_json"] = json.dumps(seo)
    cols = ", ".join(["id"] + list(fields.keys()))
    placeholders = ", ".join(["?"] * (1 + len(fields)))
    with _lock, _connect(db_path) as conn:
        conn.execute(
            f"INSERT INTO gta6_clips ({cols}) VALUES ({placeholders})",
            (clip_id, *fields.values()))


def get_clip(db_path, clip_id):
    with _lock, _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM gta6_clips WHERE id=?",
                           (clip_id,)).fetchone()
    return _row_to_clip(row) if row else None


def list_clips(db_path, status=None, limit=100):
    with _lock, _connect(db_path) as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM gta6_clips WHERE status=? "
                "ORDER BY score DESC, created_at DESC LIMIT ?",
                (status, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM gta6_clips "
                "ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [_row_to_clip(r) for r in rows]


def update_clip(db_path, clip_id, **fields):
    if not fields:
        return
    if "seo" in fields:
        fields["seo_json"] = json.dumps(fields.pop("seo"))
    sets = ", ".join(f"{k}=?" for k in fields)
    with _lock, _connect(db_path) as conn:
        conn.execute(f"UPDATE gta6_clips SET {sets} WHERE id=?",
                     (*fields.values(), clip_id))


def log_upload(db_path, clip_id, status, dry_run=1, error="",
               youtube_video_id=""):
    with _lock, _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO uploads (clip_id, youtube_video_id, status, dry_run, "
            "error) VALUES (?,?,?,?,?)",
            (clip_id or "", youtube_video_id or "", status, int(dry_run),
             error or ""))


def list_uploads(db_path, limit=50):
    with _lock, _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM uploads ORDER BY created_at DESC LIMIT ?",
            (limit,)).fetchall()
    return [dict(r) for r in rows]


def uploads_today_count(db_path) -> int:
    """Real (non-dry-run) successful uploads today (UTC)."""
    with _lock, _connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM uploads WHERE dry_run=0 AND status='uploaded' "
            "AND date(created_at) = date('now')").fetchone()
    return int(row[0]) if row else 0


def delete_old_jobs(db_path, job_root, max_age_hours=24):
    """Delete jobs (rows + files) older than max_age_hours. Best-effort."""
    import shutil
    import time
    cutoff = time.time() - max_age_hours * 3600
    with _lock, _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id FROM jobs WHERE "
            "strftime('%s', created_at) < strftime('%s', 'now', ?)",
            (f"-{max_age_hours} hours",)).fetchall()
        for (job_id,) in rows:
            conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            shutil.rmtree(Path(job_root) / job_id, ignore_errors=True)
    # Orphaned dirs with no DB row.
    root = Path(job_root)
    if root.exists():
        for d in root.iterdir():
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
