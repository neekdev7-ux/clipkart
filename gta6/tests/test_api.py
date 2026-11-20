"""API job lifecycle with mocked download/transcribe/cut (no network,
no Whisper model)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import main as app_main
from backend.app import pipeline_runner
from tests.conftest import words_from_text
from tests.test_score import FILLER_TEXT, HOOK_TEXT


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    app_main._rate_hits.clear()


@pytest.fixture()
def client(monkeypatch):
    words = words_from_text((HOOK_TEXT * 2) + (FILLER_TEXT * 3))

    monkeypatch.setattr(
        pipeline_runner.download, "get_video_info",
        lambda url: {"video_id": "test123", "title": "Money Saving Tips",
                     "thumbnail": "https://example.com/t.jpg",
                     "duration": 120, "uploader": "Tester"})
    monkeypatch.setattr(
        pipeline_runner.download, "download_video",
        lambda url, out: Path(out))
    monkeypatch.setattr(
        pipeline_runner.transcribe, "transcribe",
        lambda video_path, work_dir=None: {
            "words": words, "language": "en", "duration": 120,
            "wav_path": "/nonexistent/audio.wav"})

    def fake_cut(input_path, start, end, output_path, mode="crop",
                 captions_ass=None, crf=23):
        Path(output_path).write_bytes(b"fake-mp4-bytes")
        return Path(output_path)

    monkeypatch.setattr(pipeline_runner.cut, "cut_clip", fake_cut)

    with TestClient(app_main.app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_job_lifecycle_done(client):
    r = client.post("/api/jobs", json={
        "url": "https://www.youtube.com/watch?v=test123",
        "max_clips": 2, "clip_seconds": 45})
    assert r.status_code == 202
    job_id = r.json()["job_id"]

    # TestClient runs BackgroundTasks synchronously, but poll to be safe.
    job = None
    for _ in range(10):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            break
    assert job["status"] == "done", job.get("error")
    assert job["title"] == "Money Saving Tips"
    assert job["progress"] == 100
    assert 1 <= len(job["clips"]) <= 2
    clip = job["clips"][0]
    assert clip["score"] > 0
    assert clip["reason"]
    assert len(clip["seo"]["titles"]) == 3
    assert len(clip["seo"]["hashtags"]) >= 8

    dl = client.get(f"/api/jobs/{job_id}/clips/1/download")
    assert dl.status_code == 200
    assert dl.content == b"fake-mp4-bytes"
    assert dl.headers["content-type"] == "video/mp4"


def test_invalid_url_rejected(client):
    r = client.post("/api/jobs", json={"url": "https://example.com/not-youtube"})
    assert r.status_code == 400


def test_clip_seconds_validated(client):
    r = client.post("/api/jobs", json={
        "url": "https://www.youtube.com/watch?v=test123", "clip_seconds": 10})
    assert r.status_code == 422


def test_unknown_job_404(client):
    assert client.get("/api/jobs/doesnotexist").status_code == 404
    assert client.get("/api/jobs/doesnotexist/clips/1/download").status_code == 404


def test_frontend_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "ClipNova" in r.text
    assert "logo.webp" in r.text
