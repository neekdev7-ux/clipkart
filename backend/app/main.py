"""ClipNova API + static frontend.

Run:  uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import os
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Literal

from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..pipeline import download as download_mod
from . import pipeline_runner, store

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("CLIPNOVA_DATA", PROJECT_ROOT / "data"))
DB_PATH = DATA_DIR / "clipnova.db"
JOB_ROOT = DATA_DIR / "jobs"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

MAX_JOBS_PER_HOUR = int(os.environ.get("MAX_JOBS_PER_HOUR", "3"))

# --- MVP-grade in-memory per-IP rate limit -------------------------------
# NOTE: this resets on restart and does not work across multiple workers.
# For production, replace with a Redis-backed limiter.
_rate_hits: defaultdict[str, list] = defaultdict(list)


def _rate_limited(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _rate_hits[ip] if now - t < 3600]
    _rate_hits[ip] = hits
    if len(hits) >= MAX_JOBS_PER_HOUR:
        return True
    hits.append(now)
    return False


class JobRequest(BaseModel):
    url: str
    max_clips: int = Field(default=5, ge=1, le=10)
    clip_seconds: int = Field(default=45, ge=30, le=60)
    # "auto" detects GTA 6 from the video title / transcript;
    # "gta6" / "generic" force that mode.
    mode: Literal["auto", "gta6", "generic"] = "auto"


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init_db(DB_PATH)
    JOB_ROOT.mkdir(parents=True, exist_ok=True)
    store.delete_old_jobs(DB_PATH, JOB_ROOT)
    yield


app = FastAPI(title="ClipNova", version="1.0.0", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "clipnova"}


@app.post("/api/jobs", status_code=202)
def create_job(req: JobRequest, request: Request, background: BackgroundTasks):
    url = (req.url or "").strip()
    if not download_mod.is_youtube_url(url):
        raise HTTPException(status_code=400,
                            detail="Please paste a valid YouTube URL.")
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(ip):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit: {MAX_JOBS_PER_HOUR} jobs per hour. Try again later.")
    job_id = uuid.uuid4().hex[:12]
    store.create_job(DB_PATH, job_id, url, req.max_clips, req.clip_seconds,
                     mode=req.mode)
    background.add_task(pipeline_runner.run_pipeline, DB_PATH, JOB_ROOT, job_id)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = store.get_job(DB_PATH, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.get("/api/jobs/{job_id}/clips/{n}/download")
def download_clip(job_id: str, n: int):
    path = JOB_ROOT / job_id / "clips" / f"clip_{n}.mp4"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Clip not found.")
    return FileResponse(path, media_type="video/mp4",
                        filename=f"clipnova-clip-{n}.mp4")


@app.get("/api/jobs/{job_id}/clips/{n}/thumbnail")
def download_thumbnail(job_id: str, n: int):
    path = JOB_ROOT / job_id / "clips" / f"clip_{n}.jpg"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found.")
    return FileResponse(path, media_type="image/jpeg",
                        filename=f"clipnova-clip-{n}-thumb.jpg")


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True),
              name="frontend")
