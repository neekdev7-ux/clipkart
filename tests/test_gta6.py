"""GTA 6 mode: hype scoring, GTA 6 SEO, mode auto-detect, and the
transcription offline fix. No Whisper model or network required."""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import main as app_main
from backend.app import pipeline_runner
from backend.pipeline import gta6, score, seo, transcribe
from tests.conftest import words_from_text
from tests.test_score import FILLER_TEXT, HOOK_TEXT

GTA6_TEXT = (
    "Lucia and Jason drive through Vice City in the new GTA 6 trailer. "
    "The map leak shows Leonida Keys and Ocean Drive in open world gameplay. "
    "This heist mission ends with a police chase and a crazy getaway. "
    "Rockstar revealed the release date and the trailer two first look. "
    "Did you see what just happened in that insane shootout scene? "
)

GTA6_CLIP_TEXT = (
    "Lucia and Jason drive through Vice City in the new GTA 6 trailer. "
    "The map leak shows Leonida Keys and Ocean Drive. "
    "This heist mission ends with a police chase and a crazy getaway."
)


def _mixed_transcript():
    # ~78s of generic hook content, then ~120s of GTA 6 content.
    return words_from_text((HOOK_TEXT * 2) + (GTA6_TEXT * 4))


# ---------------------------------------------------------------------------
# Hype bonus
# ---------------------------------------------------------------------------

def test_hype_bonus_scales_with_distinct_hits_and_caps():
    assert gta6.hype_bonus("nothing relevant here") == 0.0
    assert gta6.hype_bonus("one heist") == 4.0
    assert gta6.hype_bonus("a heist and a leak") == 8.0
    # 5 distinct hits hit the cap of 20...
    assert gta6.hype_bonus("heist leak lucia jason vice") == 20.0
    # ...and more hits stay capped.
    assert gta6.hype_bonus("heist leak lucia jason vice race mission") == 20.0


def test_hype_bonus_counts_distinct_hits_only():
    assert gta6.hype_bonus("heist heist heist") == 4.0
    # "vice city" counts as phrase + the word "vice".
    assert set(gta6.hype_hits("Vice City")) == {"vice city", "vice"}


# ---------------------------------------------------------------------------
# GTA 6 ranking
# ---------------------------------------------------------------------------

def test_rank_clips_gta6_prefers_gta6_window_over_generic():
    words = _mixed_transcript()
    boundary = len(HOOK_TEXT.split()) * 2 * 0.5  # generic half ends here

    base = score.rank_clips(words, title="Money Saving Tips",
                            clip_seconds=45, max_clips=3)
    assert base[0]["start"] < boundary, "base ranker should pick the hook half"

    ranked = gta6.rank_clips_gta6(words, title="Money Saving Tips",
                                  clip_seconds=45, max_clips=3)
    assert ranked, "expected GTA 6 clips"
    assert ranked[0]["start"] >= boundary, \
        "GTA 6 ranker should pick the GTA 6 half"
    assert "GTA 6" in ranked[0]["reason"]
    assert 30 <= ranked[0]["duration"] <= 60

    # The preference comes from the GTA 6 bonus, not the base score:
    # the GTA 6 top window scores LOWER on the base scorer than the
    # generic top window.
    windows = {round(w["start"], 2): w
               for w in score.build_windows(words, clip_seconds=45)}
    base_of_gta6_top = score.score_window(
        windows[round(ranked[0]["start"], 2)], words,
        title="Money Saving Tips")[0]
    base_of_base_top = score.score_window(
        windows[round(base[0]["start"], 2)], words,
        title="Money Saving Tips")[0]
    assert base_of_gta6_top < base_of_base_top


def test_score_window_gta6_adds_bonus_over_base():
    words = words_from_text(GTA6_TEXT * 4)
    window = score.build_windows(words, clip_seconds=45)[0]
    base_s, _ = score.score_window(window, words, title="GTA 6 Gameplay")
    gta_s, reason = gta6.score_window_gta6(window, words,
                                           title="GTA 6 Gameplay")
    assert gta_s > base_s
    assert gta_s <= 100.0
    assert "GTA 6" in reason


def test_rank_clips_gta6_empty_transcript():
    assert gta6.rank_clips_gta6([], title="GTA 6") == []


# ---------------------------------------------------------------------------
# GTA 6 SEO
# ---------------------------------------------------------------------------

def test_generate_seo_gta6_mode():
    pack = seo.generate_seo(GTA6_CLIP_TEXT, video_title="GTA 6 Gameplay",
                            mode="gta6")
    assert len(pack["titles"]) == 3
    assert len(set(pack["titles"])) == 3
    assert all(len(t) <= 100 for t in pack["titles"])
    assert all("gta 6" in t.lower() or "gta vi" in t.lower()
               for t in pack["titles"])
    for tag in ("#gta6", "#gtavi", "#grandtheftauto6", "#vicecity"):
        assert tag in pack["hashtags"]
    assert 8 <= len(pack["hashtags"]) <= 12
    for tag in ("gta 6", "gta vi", "grand theft auto 6", "vice city",
                "rockstar games", "gta 6 gameplay", "gta 6 shorts"):
        assert tag in pack["tags"]
    assert 8 <= len(pack["tags"]) <= 12
    assert pack["description"].strip()


def test_generate_seo_default_mode_is_generic():
    pack_default = seo.generate_seo(GTA6_CLIP_TEXT, video_title="GTA 6 Gameplay")
    pack_generic = seo.generate_seo(GTA6_CLIP_TEXT, video_title="GTA 6 Gameplay",
                                    mode="generic")
    assert pack_default == pack_generic
    # Generic mode does not force GTA 6 into every title.
    assert not all("gta 6" in t.lower() for t in pack_default["titles"])


# ---------------------------------------------------------------------------
# Mode auto-detect
# ---------------------------------------------------------------------------

def test_resolve_mode_title_detects_gta6():
    generic_words = words_from_text(FILLER_TEXT * 4)
    for title in ("GTA 6 Trailer Reaction", "GTA VI Gameplay",
                  "Grand Theft Auto 6 Leaks", "gta6 - first look"):
        assert pipeline_runner.resolve_mode("auto", title, generic_words) == "gta6"


def test_resolve_mode_transcript_detects_gta6():
    gta_words = words_from_text(GTA6_TEXT * 4)
    assert pipeline_runner.resolve_mode("auto", "Some Random Video",
                                        gta_words) == "gta6"


def test_resolve_mode_generic_otherwise():
    generic_words = words_from_text((HOOK_TEXT * 2) + (FILLER_TEXT * 3))
    assert pipeline_runner.resolve_mode("auto", "Money Saving Tips",
                                        generic_words) == "generic"
    # Fewer than 3 distinct GTA 6 hits must not flip the mode.
    few_hits = words_from_text(
        ("One secret about saving money. " * 20) + (FILLER_TEXT * 4))
    assert pipeline_runner.resolve_mode("auto", "Money Saving Tips",
                                        few_hits) == "generic"
    # Explicit requests win over detection either way.
    gta_words = words_from_text(GTA6_TEXT * 4)
    assert pipeline_runner.resolve_mode("generic", "GTA 6 Trailer",
                                        gta_words) == "generic"
    assert pipeline_runner.resolve_mode("gta6", "Money Saving Tips",
                                        generic_words) == "gta6"


# ---------------------------------------------------------------------------
# Transcription offline fix (cached-model detection only; no Whisper import)
# ---------------------------------------------------------------------------

def test_model_is_cached_detects_hf_cache(tmp_path, monkeypatch):
    hub = tmp_path / "hub"
    cached = (hub / "models--Systran--faster-whisper-tiny"
              / "snapshots" / "abc123")
    cached.mkdir(parents=True)
    (cached / "model.bin").write_bytes(b"fake")
    monkeypatch.setenv("HF_HUB_CACHE", str(hub))
    assert transcribe._model_is_cached("tiny") is True
    assert transcribe._model_is_cached("base") is False
    assert transcribe._model_is_cached("Systran/faster-whisper-tiny") is True
    assert transcribe._model_is_cached(str(cached)) is True  # local path


def test_use_local_model_sets_offline_only_when_cached(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hub"))
    # Model missing: must NOT go offline, so the first run can download it.
    transcribe._use_local_model_if_cached("tiny")
    assert "HF_HUB_OFFLINE" not in os.environ
    cached = (tmp_path / "hub" / "models--Systran--faster-whisper-tiny"
              / "snapshots" / "abc123")
    cached.mkdir(parents=True)
    (cached / "model.bin").write_bytes(b"fake")
    transcribe._use_local_model_if_cached("tiny")
    assert os.environ["HF_HUB_OFFLINE"] == "1"


# ---------------------------------------------------------------------------
# API: mode field + resolved mode stored on the job
# ---------------------------------------------------------------------------

@pytest.fixture()
def gta_client(monkeypatch):
    words = words_from_text(GTA6_TEXT * 4)
    app_main._rate_hits.clear()

    monkeypatch.setattr(
        pipeline_runner.download, "get_video_info",
        lambda url: {"video_id": "gta123", "title": "GTA 6 Trailer Reaction",
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


def _wait_done(client, job_id):
    job = None
    for _ in range(10):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
    return job


def test_job_mode_auto_detects_gta6(gta_client):
    r = gta_client.post("/api/jobs", json={
        "url": "https://www.youtube.com/watch?v=gta123",
        "max_clips": 2, "clip_seconds": 45})
    assert r.status_code == 202
    job = _wait_done(gta_client, r.json()["job_id"])
    assert job["status"] == "done", job.get("error")
    assert job["mode"] == "gta6"
    assert job["clips"]
    assert "#gta6" in job["clips"][0]["seo"]["hashtags"]
    assert "gta 6" in job["clips"][0]["seo"]["tags"]


def test_job_mode_explicit_generic_overrides_title(gta_client):
    r = gta_client.post("/api/jobs", json={
        "url": "https://www.youtube.com/watch?v=gta123",
        "max_clips": 1, "clip_seconds": 45, "mode": "generic"})
    assert r.status_code == 202
    job = _wait_done(gta_client, r.json()["job_id"])
    assert job["status"] == "done", job.get("error")
    assert job["mode"] == "generic"
    assert "#gta6" not in job["clips"][0]["seo"]["hashtags"]


def test_job_mode_invalid_rejected(gta_client):
    r = gta_client.post("/api/jobs", json={
        "url": "https://www.youtube.com/watch?v=gta123", "mode": "fortnite"})
    assert r.status_code == 422
