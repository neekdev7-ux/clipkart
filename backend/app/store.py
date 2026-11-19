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
