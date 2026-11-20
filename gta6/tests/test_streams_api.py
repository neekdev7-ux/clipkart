"""GTA 6 API: streams watchlist, clip queue approve/reject/upload,
queue + status endpoints. Discovery, recorder and uploader are all
mocked — no network, no ffmpeg, no YouTube API."""
import pytest
from fastapi.testclient import TestClient

from backend.app import main as app_main
from backend.app import store


class FakeUploader:
    def quota(self, db_path):
        return {"uploads_today": 0, "max_uploads_per_day": 6,
                "quota_units_used": 0, "quota_units_daily": 10000,
                "uploads_remaining": 6}

    def is_authorized(self):
        return False

    def is_configured(self):
        return False

    def upload_clip(self, db_path, clip, file_path, title=None,
                    description=None, tags=None):
        store.log_upload(db_path, clip["id"], status="simulated",
                         dry_run=1)
        return {"dry_run": True, "status": "simulated",
                "title": title or "GTA 6 Shorts",
                "message": "Dry-run: nothing was sent to YouTube."}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(app_main, "get_uploader", lambda: FakeUploader())

    async def _fake_start():
        app_main.monitor.running = True
        return True

    async def _fake_stop():
        app_main.monitor.running = False
        return True

    monkeypatch.setattr(app_main.monitor, "start", _fake_start)
    monkeypatch.setattr(app_main.monitor, "stop", _fake_stop)
    monkeypatch.setattr(app_main.monitor, "state", lambda: {
        "running": app_main.monitor.running,
        "started_at": None, "last_discovery": None, "last_error": "",
        "stats": {"discovered": 0, "recorded": 0, "clips": 0, "uploaded": 0},
        "auto_upload": False, "queries": ["GTA 6 live"],
        "watched": [], "disk_bytes": 0, "disk_cap_bytes": 1})

    with TestClient(app_main.app) as c:
        yield c
    app_main.monitor.running = False


def _seed_clip(clip_id="clip-abc", status="detected"):
    store.create_clip(
        app_main.DB_PATH, clip_id,
        stream_id="stream-1", stream_title="GTA 6 Live",
        stream_url="https://www.youtube.com/watch?v=abc123",
        channel="StreamerBhai", segment_file="/tmp/seg.mp4",
        start=0.0, end=45.0, duration=45.0, score=88.5,
        reason="Strong hook + GTA 6 hype peak", text="Bhai dekh Vice City!",
        seo={"titles": ["GTA 6 Vice City — You Have to See This"],
             "description": "Test", "hashtags": ["#GTA6"],
             "tags": ["gta 6"]},
        file_path=str(app_main.DATA_DIR / "clips" / f"{clip_id}.mp4"),
        status=status)
    return clip_id


def test_health_gta6(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["service"] == "clipnova-gta6"


def test_streams_empty_then_watch_url(client, monkeypatch):
    assert client.get("/api/streams").json()["streams"] == []

    def fake_info(url):
        return {"video_id": "live1234567", "title": "GTA 6 Gameplay LIVE",
                "channel": "StreamerBhai", "viewers": 1200,
                "thumbnail": "", "is_live": True,
                "url": "https://www.youtube.com/watch?v=live1234567",
                "hls_url": "https://example.com/live.m3u8"}

    monkeypatch.setattr(app_main.discovery, "get_stream_info", fake_info)
    r = client.post("/api/streams/watch",
                    json={"url": "https://www.youtube.com/watch?v=live1234567"})
    assert r.status_code == 201
    added = r.json()["added"]
    assert len(added) == 1
    assert added[0]["title"] == "GTA 6 Gameplay LIVE"
    assert added[0]["viewers"] == 1200

    streams = client.get("/api/streams").json()["streams"]
    assert any(s["video_id"] == "live1234567" for s in streams)

    # Watching the same stream again returns the existing row.
    r2 = client.post("/api/streams/watch",
                     json={"url": "https://www.youtube.com/watch?v=live1234567"})
    assert r2.status_code == 201
    assert r2.json()["added"][0]["id"] == added[0]["id"]


def test_watch_rejects_non_live_and_bad_url(client, monkeypatch):
    monkeypatch.setattr(
        app_main.discovery, "get_stream_info",
        lambda url: {"video_id": "vid123", "title": "Old VOD",
                     "channel": "X", "viewers": 0, "is_live": False,
                     "url": url, "hls_url": ""})
    r = client.post("/api/streams/watch",
                    json={"url": "https://www.youtube.com/watch?v=vid123"})
    assert r.status_code == 400
    assert "not a live stream" in r.json()["detail"]

    r = client.post("/api/streams/watch",
                    json={"url": "https://example.com/nope"})
    assert r.status_code == 400

    r = client.post("/api/streams/watch", json={})
    assert r.status_code == 400


def test_watch_query_adds_found_streams(client, monkeypatch):
    monkeypatch.setattr(
        app_main.discovery, "discover_live_streams",
        lambda queries, api_key=None, min_viewers=10: [
            {"video_id": "q1", "url": "https://www.youtube.com/watch?v=q1",
             "title": "GTA 6 Leak Stream", "channel": "LeakGuy",
             "viewers": 500, "thumbnail": ""}])
    r = client.post("/api/streams/watch", json={"query": "GTA 6 leak"})
    assert r.status_code == 201
    assert r.json()["added"][0]["video_id"] == "q1"


def test_watch_query_no_results_404(client, monkeypatch):
    monkeypatch.setattr(
        app_main.discovery, "discover_live_streams",
        lambda *a, **k: [])
    r = client.post("/api/streams/watch", json={"query": "nothing live"})
    assert r.status_code == 404


def test_unwatch_stream(client, monkeypatch):
    monkeypatch.setattr(
        app_main.discovery, "get_stream_info",
        lambda url: {"video_id": "del123", "title": "To Delete",
                     "channel": "X", "viewers": 10, "is_live": True,
                     "url": url, "hls_url": ""})
    added = client.post(
        "/api/streams/watch",
        json={"url": "https://www.youtube.com/watch?v=del123"}).json()["added"][0]
    r = client.delete(f"/api/streams/{added['id']}")
    assert r.status_code == 200
    assert r.json()["deleted"] == added["id"]
    assert client.delete("/api/streams/nope").status_code == 404


def test_clip_approve_reject_flow(client):
    clip_id = _seed_clip("clip-flow")
    r = client.post(f"/api/clips/{clip_id}/approve")
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    clip2 = _seed_clip("clip-flow2")
    r = client.post(f"/api/clips/{clip2}/reject")
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"

    assert client.post("/api/clips/nope/approve").status_code == 404
    assert client.post("/api/clips/nope/reject").status_code == 404


def test_clip_upload_dry_run(client):
    clip_id = _seed_clip("clip-upload")
    r = client.post(f"/api/clips/{clip_id}/upload")
    assert r.status_code == 200
    data = r.json()
    assert data["dry_run"] is True
    assert data["status"] == "simulated"
    # Dry-run does NOT mark the clip uploaded.
    clip = client.get("/api/clips?status=detected").json()["clips"]
    assert any(c["id"] == clip_id for c in clip)


def test_clip_upload_rejected_blocked(client):
    clip_id = _seed_clip("clip-rej", status="rejected")
    r = client.post(f"/api/clips/{clip_id}/upload")
    assert r.status_code == 400


def test_clip_download(client):
    clip_id = _seed_clip("clip-dl")
    path = app_main.DATA_DIR / "clips" / f"{clip_id}.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake-clip-bytes")
    r = client.get(f"/api/clips/{clip_id}/download")
    assert r.status_code == 200
    assert r.content == b"fake-clip-bytes"
    assert r.headers["content-type"] == "video/mp4"
    assert client.get("/api/clips/nope/download").status_code == 404


def test_queue_and_status(client):
    _seed_clip("clip-q")
    q = client.get("/api/queue").json()
    assert "pending" in q and "uploads" in q and "quota" in q
    assert any(c["id"] == "clip-q" for c in q["pending"])
    assert q["quota"]["max_uploads_per_day"] == 6
    assert q["auto_upload"] is False

    s = client.get("/api/status").json()
    assert "running" in s and "quota" in s and "youtube" in s
    assert s["youtube"]["authorized"] is False


def test_monitor_start_stop(client):
    r = client.post("/api/monitor/start")
    assert r.status_code == 200
    assert r.json()["running"] is True
    r = client.post("/api/monitor/stop")
    assert r.status_code == 200
    assert r.json()["running"] is False


def test_auth_requires_configuration(client, monkeypatch):
    # FakeUploader has no get_auth_url; use a real unconfigured uploader.
    from backend.youtube_uploader import YouTubeUploader
    monkeypatch.delenv("YOUTUBE_CLIENT_ID", raising=False)
    monkeypatch.delenv("YOUTUBE_CLIENT_SECRET", raising=False)
    real = YouTubeUploader(data_dir=app_main.DATA_DIR, auto_upload=False,
                           client_secret_file=app_main.DATA_DIR / "nope.json")
    monkeypatch.setattr(app_main, "get_uploader", lambda: real)
    r = client.get("/auth/youtube", follow_redirects=False)
    assert r.status_code == 400
    assert "not configured" in r.json()["detail"]


def test_dashboard_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "GTA 6 Edition" in r.text
    assert "logo.webp" in r.text
    assert "Live monitor" in r.text
