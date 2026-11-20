"""Uploader safety: dry-run NEVER calls the YouTube API, the quota
guard blocks over-limit uploads, and every attempt is logged.
No network, no real credentials — all state is a temp SQLite DB."""
import pytest

from backend.app import store
from backend.youtube_uploader import UploadBlocked, YouTubeUploader


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "uploader.db"
    store.init_db(path)
    return path


def _clip(clip_id="clip1"):
    return {
        "id": clip_id,
        "seo": {"titles": ["GTA 6 Vice City — You Have to See This"],
                "description": "Test description",
                "tags": ["gta 6", "vice city"]},
    }


def _uploader(tmp_path, **kw):
    kw.setdefault("data_dir", tmp_path)
    kw.setdefault("token_file", tmp_path / "token.json")
    kw.setdefault("client_secret_file", tmp_path / "no-such-secret.json")
    return YouTubeUploader(**kw)


def test_dry_run_never_calls_api(db, tmp_path, monkeypatch):
    up = _uploader(tmp_path, auto_upload=False)
    monkeypatch.setattr(
        up, "build_service",
        lambda: (_ for _ in ()).throw(
            AssertionError("YouTube API must not be called in dry-run")))
    result = up.upload_clip(db, _clip(), tmp_path / "clip.mp4")
    assert result["dry_run"] is True
    assert result["status"] == "simulated"
    uploads = store.list_uploads(db)
    assert len(uploads) == 1
    assert uploads[0]["status"] == "simulated"
    assert uploads[0]["dry_run"] == 1
    assert uploads[0]["clip_id"] == "clip1"


def test_dry_run_is_default(db, tmp_path, monkeypatch):
    up = _uploader(tmp_path)  # no auto_upload passed
    assert up.auto_upload is False
    monkeypatch.setattr(
        up, "build_service",
        lambda: (_ for _ in ()).throw(AssertionError("API called")))
    result = up.upload_clip(db, _clip(), tmp_path / "clip.mp4")
    assert result["dry_run"] is True


def test_quota_guard_blocks_over_limit(db, tmp_path, monkeypatch):
    up = _uploader(tmp_path, auto_upload=True, max_uploads_per_day=2)
    monkeypatch.setattr(up, "is_authorized", lambda: True)
    # Seed 2 real uploads today.
    store.log_upload(db, "a", status="uploaded", dry_run=0)
    store.log_upload(db, "b", status="uploaded", dry_run=0)
    assert up.uploads_today(db) == 2
    allowed, reason = up.can_upload(db)
    assert allowed is False
    assert "limit" in reason.lower()
    with pytest.raises(UploadBlocked, match="limit"):
        up.upload_clip(db, _clip(), tmp_path / "clip.mp4")
    # The blocked attempt is logged too.
    blocked = [u for u in store.list_uploads(db) if u["status"] == "blocked"]
    assert len(blocked) == 1


def test_quota_counts_only_real_uploads(db, tmp_path):
    up = _uploader(tmp_path, auto_upload=True, max_uploads_per_day=6)
    store.log_upload(db, "a", status="simulated", dry_run=1)
    store.log_upload(db, "b", status="blocked", dry_run=0)
    store.log_upload(db, "c", status="failed", dry_run=0)
    store.log_upload(db, "d", status="uploaded", dry_run=0)
    assert up.uploads_today(db) == 1
    q = up.quota(db)
    assert q["uploads_today"] == 1
    assert q["quota_units_used"] == 1600
    assert q["quota_units_daily"] == 10000
    assert q["uploads_remaining"] == 5


def test_auth_gate_blocks_without_token(db, tmp_path):
    up = _uploader(tmp_path, auto_upload=True)
    assert up.is_authorized() is False
    allowed, reason = up.can_upload(db)
    assert allowed is False
    assert "token" in reason.lower() or "auth" in reason.lower()


def test_not_configured_without_credentials(tmp_path):
    up = _uploader(tmp_path, client_id="", client_secret="")
    assert up.is_configured() is False
    with pytest.raises(UploadBlocked, match="not configured"):
        up.get_auth_url("http://localhost:8000/auth/youtube/callback")


def test_configured_with_env_credentials(tmp_path):
    up = _uploader(tmp_path, client_id="id-123", client_secret="secret-123")
    assert up.is_configured() is True
    cfg = up.client_config()
    assert cfg["web"]["client_id"] == "id-123"


def test_upload_requires_existing_file_when_live(db, tmp_path, monkeypatch):
    up = _uploader(tmp_path, auto_upload=True)
    monkeypatch.setattr(up, "is_authorized", lambda: True)
    with pytest.raises(UploadBlocked, match="not found"):
        up.upload_clip(db, _clip(), tmp_path / "missing.mp4")
