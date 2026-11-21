"""ClipNova GTA 6 Edition — API server + dashboard.

Always-on API server: watches YouTube GTA 6 live streams, auto-detects
viral moments, cuts vertical Shorts with captions + GTA 6 SEO, and
uploads them to YouTube (dry-run by default; real uploads only with
AUTO_UPLOAD=true and a valid OAuth token).

Run:  uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..config import settings
from ..pipeline import download as download_mod
from ..streams import discovery
from ..youtube_uploader import UploadBlocked, YouTubeUploader
from . import monitor as monitor_mod
from . import pipeline_runner, store

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = settings.data_dir
DB_PATH = settings.db_path
JOB_ROOT = settings.job_root
CLIP_ROOT = settings.clip_root
FRONTEND_DIR = PROJECT_ROOT / "frontend"

MAX_JOBS_PER_HOUR = settings.max_jobs_per_hour

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


# --- singletons -------------------------------------------------------------
_uploader = None
monitor = monitor_mod.Monitor(settings)
_oauth_states: dict = {}  # state -> redirect_uri (in-memory, single process)


def get_uploader() -> YouTubeUploader:
    global _uploader
    if _uploader is None:
        _uploader = YouTubeUploader(
            data_dir=DATA_DIR, auto_upload=settings.auto_upload,
            max_uploads_per_day=settings.max_uploads_per_day,
            client_id=settings.youtube_client_id or None,
            client_secret=settings.youtube_client_secret or None,
            client_secret_file=settings.client_secret_path,
            token_file=settings.token_path)
    return _uploader


class JobRequest(BaseModel):
    url: str
    max_clips: int = Field(default=5, ge=1, le=10)
    clip_seconds: int = Field(default=45, ge=30, le=60)


class WatchRequest(BaseModel):
    url: str = ""
    query: str = ""


class UploadRequest(BaseModel):
    title: str = ""
    description: str = ""
    tags: list = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init_db(DB_PATH)
    # A restart leaves "recording" rows whose ffmpeg is gone; mark them
    # "watching" again so the monitor can pick them up fresh.
    for s in store.list_streams(DB_PATH, status="recording"):
        store.update_stream(DB_PATH, s["id"], status="watching", error="")
    JOB_ROOT.mkdir(parents=True, exist_ok=True)
    CLIP_ROOT.mkdir(parents=True, exist_ok=True)
    settings.stream_root.mkdir(parents=True, exist_ok=True)
    store.delete_old_jobs(DB_PATH, JOB_ROOT)
    monitor.uploader = get_uploader()
    if settings.monitor_on_start:
        await monitor.start()
    yield
    if monitor.running:
        await monitor.stop()


app = FastAPI(title="ClipNova GTA 6 Edition", version="2.0.0",
              lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "clipnova-gta6",
            "auto_upload": settings.auto_upload,
            "monitor_running": monitor.running}


# ---------------------------------------------------------------------------
# Original feature: cut Shorts from any YouTube video (kept as-is)
# ---------------------------------------------------------------------------

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
    store.create_job(DB_PATH, job_id, url, req.max_clips, req.clip_seconds)
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


# ---------------------------------------------------------------------------
# Streams: watchlist
# ---------------------------------------------------------------------------

@app.get("/api/streams")
def list_streams(status: str = ""):
    return {"streams": store.list_streams(
        DB_PATH, status=status or None)}


@app.post("/api/streams/watch", status_code=201)
def watch_stream(req: WatchRequest):
    url = (req.url or "").strip()
    query = (req.query or "").strip()
    added = []
    if url:
        if not download_mod.is_youtube_url(url):
            raise HTTPException(status_code=400,
                                detail="Please paste a valid YouTube URL.")
        try:
            info = discovery.get_stream_info(url)
        except Exception as exc:  # noqa: BLE001 - surface lookup failures
            raise HTTPException(status_code=502,
                                detail=f"Could not read that stream: {exc}")
        if not info.get("is_live"):
            raise HTTPException(status_code=400,
                                detail="That video is not a live stream.")
        existing = store.get_stream_by_video_id(DB_PATH, info["video_id"])
        if existing:
            return {"added": [existing]}
        stream_id = uuid.uuid4().hex[:12]
        store.create_stream(
            DB_PATH, stream_id, info["video_id"], info["url"],
            title=info["title"], channel=info["channel"],
            viewers=info["viewers"],
            segments_dir=str(settings.stream_root / info["video_id"]))
        added.append(store.get_stream(DB_PATH, stream_id))
    elif query:
        found = discovery.discover_live_streams(
            [query], api_key=settings.youtube_api_key or None,
            min_viewers=settings.min_viewers)
        for s in found[:3]:
            if store.get_stream_by_video_id(DB_PATH, s["video_id"]):
                continue
            stream_id = uuid.uuid4().hex[:12]
            store.create_stream(
                DB_PATH, stream_id, s["video_id"], s["url"],
                title=s["title"], channel=s["channel"], viewers=s["viewers"],
                segments_dir=str(settings.stream_root / s["video_id"]))
            added.append(store.get_stream(DB_PATH, stream_id))
        if not added:
            raise HTTPException(status_code=404,
                                detail="No live streams found for that query.")
    else:
        raise HTTPException(status_code=400,
                            detail="Send a stream url or a search query.")
    return {"added": added}


@app.delete("/api/streams/{stream_id}")
def unwatch_stream(stream_id: str):
    stream = store.get_stream(DB_PATH, stream_id)
    if not stream:
        raise HTTPException(status_code=404, detail="Stream not found.")
    rec = monitor._recorders.pop(stream_id, None)
    if rec is not None:
        rec.stop()
    det = monitor._chat.pop(stream_id, None)
    if det is not None:
        det.stop()
    store.delete_stream(DB_PATH, stream_id)
    return {"deleted": stream_id}


# ---------------------------------------------------------------------------
# Clips: detected queue + approval + upload
# ---------------------------------------------------------------------------

@app.get("/api/clips")
def list_clips(status: str = ""):
    return {"clips": store.list_clips(DB_PATH, status=status or None)}


@app.post("/api/clips/{clip_id}/approve")
def approve_clip(clip_id: str):
    clip = store.get_clip(DB_PATH, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found.")
    if clip["status"] == "uploaded":
        raise HTTPException(status_code=400, detail="Clip already uploaded.")
    store.update_clip(DB_PATH, clip_id, status="approved")
    return store.get_clip(DB_PATH, clip_id)


@app.post("/api/clips/{clip_id}/reject")
def reject_clip(clip_id: str):
    clip = store.get_clip(DB_PATH, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found.")
    if clip["status"] == "uploaded":
        raise HTTPException(status_code=400, detail="Clip already uploaded.")
    store.update_clip(DB_PATH, clip_id, status="rejected")
    return store.get_clip(DB_PATH, clip_id)


@app.post("/api/clips/{clip_id}/upload")
def upload_clip(clip_id: str, req: UploadRequest | None = None):
    clip = store.get_clip(DB_PATH, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found.")
    if clip["status"] == "uploaded":
        raise HTTPException(status_code=400, detail="Clip already uploaded.")
    if clip["status"] == "rejected":
        raise HTTPException(status_code=400,
                            detail="Clip was rejected — approve it first.")
    uploader = get_uploader()
    try:
        result = uploader.upload_clip(
            DB_PATH, clip, clip["file_path"],
            title=(req.title if req and req.title else None),
            description=(req.description if req and req.description else None),
            tags=(req.tags if req and req.tags else None))
    except UploadBlocked as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if result.get("status") == "uploaded":
        monitor.stats["uploaded"] += 1
    return result


@app.get("/api/clips/{clip_id}/download")
def download_gta6_clip(clip_id: str):
    clip = store.get_clip(DB_PATH, clip_id)
    if not clip or not clip.get("file_path"):
        raise HTTPException(status_code=404, detail="Clip not found.")
    path = Path(clip["file_path"]).resolve()
    if not str(path).startswith(str(DATA_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Clip path not allowed.")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Clip file not found.")
    return FileResponse(path, media_type="video/mp4",
                        filename=f"clipnova-gta6-{clip_id}.mp4")


# ---------------------------------------------------------------------------
# Queue, status, monitor control
# ---------------------------------------------------------------------------

@app.get("/api/queue")
def get_queue():
    uploader = get_uploader()
    pending = (store.list_clips(DB_PATH, status="detected")
               + store.list_clips(DB_PATH, status="approved"))
    return {
        "pending": pending,
        "uploads": store.list_uploads(DB_PATH),
        "quota": uploader.quota(DB_PATH),
        "auto_upload": settings.auto_upload,
        "authorized": uploader.is_authorized(),
        "configured": uploader.is_configured(),
    }


@app.get("/api/status")
def get_status():
    uploader = get_uploader()
    state = monitor.state()
    state["quota"] = uploader.quota(DB_PATH)
    state["youtube"] = {
        "configured": uploader.is_configured(),
        "authorized": uploader.is_authorized(),
        "auto_upload": settings.auto_upload,
    }
    state["retention_hours"] = settings.retention_hours
    state["segment_minutes"] = settings.segment_minutes
    return state


@app.post("/api/monitor/start")
async def start_monitor():
    started = await monitor.start()
    return {"running": monitor.running,
            "started": started}


@app.post("/api/monitor/stop")
async def stop_monitor():
    await monitor.stop()
    return {"running": False}


# ---------------------------------------------------------------------------
# YouTube OAuth (browser flow for the channel owner)
# ---------------------------------------------------------------------------

def _redirect_uri(request: Request) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/auth/youtube/callback"


@app.get("/auth/youtube")
def auth_start(request: Request):
    uploader = get_uploader()
    try:
        url, state = uploader.get_auth_url(_redirect_uri(request))
    except UploadBlocked as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _oauth_states[state] = _redirect_uri(request)
    return RedirectResponse(url)


@app.get("/auth/youtube/callback")
def auth_callback(request: Request, code: str = "", state: str = "",
                  error: str = ""):
    if error:
        raise HTTPException(status_code=400,
                            detail=f"YouTube authorization failed: {error}")
    redirect_uri = _oauth_states.pop(state, None)
    if not redirect_uri or not code:
        raise HTTPException(status_code=400,
                            detail="Invalid or expired OAuth state — "
                                   "start again at /auth/youtube.")
    uploader = get_uploader()
    try:
        uploader.exchange_code(code, state, redirect_uri)
    except Exception as exc:  # noqa: BLE001 - surface the OAuth error
        raise HTTPException(status_code=400,
                            detail=f"Token exchange failed: {exc}")
    return RedirectResponse("/?youtube=connected")


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True),
              name="frontend")
