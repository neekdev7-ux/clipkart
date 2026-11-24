"""Resume a ClipNova job from its already-downloaded video.mp4.

Usage: python recover_job.py <job_id>

For jobs whose server process died mid-pipeline (e.g. a VM/service
restart) after the download finished: re-runs transcribe -> score ->
cut -> thumbnail -> SEO against the existing video file instead of
re-downloading. Run with nohup in the background for long videos.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.app import pipeline_runner, store  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("CLIPNOVA_DATA", PROJECT_ROOT / "data"))
DB_PATH = DATA_DIR / "clipnova.db"
JOB_ROOT = DATA_DIR / "jobs"


def main(job_id: str) -> int:
    job = store.get_job(DB_PATH, job_id)
    if not job:
        print(f"job not found: {job_id}")
        return 1
    video_path = JOB_ROOT / job_id / "video.mp4"
    if not video_path.exists() or video_path.stat().st_size == 0:
        print(f"no downloaded video for job {job_id} at {video_path}")
        return 1
    print(f"resuming job {job_id}: {job.get('title')}")
    print(f"video: {video_path} ({video_path.stat().st_size / 1e9:.2f} GB)")
    info = {"title": job.get("title") or "",
            "thumbnail": job.get("thumbnail") or "",
            "duration": job.get("duration") or 0}
    pipeline_runner.run_from_video(DB_PATH, JOB_ROOT, job_id, video_path,
                                   info)
    final = store.get_job(DB_PATH, job_id)
    print(f"job {job_id} finished: {final.get('status')} "
          f"({len(final.get('clips') or [])} clips)")
    if final.get("error"):
        print(f"error: {final['error']}")
    return 0 if final.get("status") == "done" else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
