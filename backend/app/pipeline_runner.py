"""Background pipeline: info -> download -> transcribe -> score ->
cut+caption -> SEO. Updates the job row as it goes.
"""
from __future__ import annotations

import re
import traceback
from pathlib import Path

from ..pipeline import (captions, cut, download, gta6, score, seo,
                      thumbnails, transcribe)
from . import store

_GTA6_TITLE_RE = re.compile(r"gta\s*6|gta\s*vi|grand theft auto", re.IGNORECASE)
# Transcript-based detection needs this many DISTINCT GTA 6 lexicon hits
# (a single "secret" or "race" must not flip a generic video to GTA 6).
_GTA6_MIN_DISTINCT_HITS = 3


def resolve_mode(requested, title, words):
    """Resolve the job's scoring/SEO mode.

    An explicit "gta6"/"generic" request wins. "auto" (or anything else)
    detects GTA 6 from the video title, else from the transcript
    (>=3 distinct GTA 6 lexicon hits); otherwise generic.
    """
    if requested in ("gta6", "generic"):
        return requested
    if _GTA6_TITLE_RE.search(title or ""):
        return "gta6"
    text = " ".join(w["word"] for w in (words or []))
    if len(set(gta6.hype_hits(text))) >= _GTA6_MIN_DISTINCT_HITS:
        return "gta6"
    return "generic"


def run_pipeline(db_path, job_root, job_id):
    """Full pipeline: info -> download -> transcribe -> score -> cut."""
    job_dir = Path(job_root) / job_id
    clips_dir = job_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    def progress(pct, message, status="processing"):
        store.update_job(db_path, job_id, progress=pct, message=message,
                         status=status)

    try:
        job = store.get_job(db_path, job_id)
        url = job["url"]

        progress(5, "Fetching video info...")
        info = download.get_video_info(url)
        store.update_job(db_path, job_id, title=info["title"],
                         thumbnail=info["thumbnail"],
                         duration=info["duration"])

        progress(20, "Downloading video...")
        video_path = download.download_video(url, job_dir / "video.mp4")
    except Exception as exc:  # noqa: BLE001 - surface any failure on the job
        traceback.print_exc()
        store.update_job(db_path, job_id, status="failed", error=str(exc),
                         message="Failed")
        return

    run_from_video(db_path, job_root, job_id, video_path, info)


def run_from_video(db_path, job_root, job_id, video_path, info):
    """Pipeline from an already-downloaded video: transcribe -> score ->
    cut+caption -> thumbnail -> SEO. Updates the job row as it goes.

    Used by run_pipeline after downloading, and by recover_job.py to
    resume a job whose download survived a server restart.
    """
    job_dir = Path(job_root) / job_id
    clips_dir = job_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    def progress(pct, message, status="processing"):
        store.update_job(db_path, job_id, progress=pct, message=message,
                         status=status)

    try:
        job = store.get_job(db_path, job_id)
        max_clips = job["max_clips"]
        clip_seconds = job["clip_seconds"]
        requested_mode = job.get("mode") or "auto"

        progress(45, "Transcribing audio (Whisper)...")
        result = transcribe.transcribe(video_path, work_dir=job_dir)
        words = result["words"]
        if len(words) < 20:
            raise RuntimeError("Transcript too short — is there speech in this video?")
        energy = score.compute_energy_profile(result["wav_path"])

        mode = resolve_mode(requested_mode, info["title"], words)
        store.update_job(db_path, job_id, mode=mode)

        progress(65, "Finding viral moments...")
        if mode == "gta6":
            ranked = gta6.rank_clips_gta6(words, title=info["title"],
                                          clip_seconds=clip_seconds,
                                          max_clips=max_clips, energy=energy)
        else:
            ranked = score.rank_clips(words, title=info["title"],
                                      clip_seconds=clip_seconds,
                                      max_clips=max_clips, energy=energy)
        if not ranked:
            raise RuntimeError("Video too short to cut 30s clips from.")

        clips = []
        for i, clip in enumerate(ranked):
            pct = 70 + int(25 * (i + 1) / len(ranked))
            progress(pct, f"Cutting clip {i + 1} of {len(ranked)}...")
            out_path = clips_dir / f"clip_{i + 1}.mp4"
            ass_path = clips_dir / f"clip_{i + 1}.ass"
            captions.build_ass(words, clip["start"], clip["end"], ass_path)
            try:
                cut.cut_clip(video_path, clip["start"], clip["end"], out_path,
                             mode="crop", captions_ass=ass_path)
            except Exception:
                # Captions burn can fail if fonts are missing; fall back to
                # the same cut without burned captions rather than failing.
                cut.cut_clip(video_path, clip["start"], clip["end"], out_path,
                             mode="crop")
            # Per-clip keywords: job-level keywords made every clip's SEO
            # pack identical (same titles/hashtags/tags). Extracting from
            # the clip's own text gives each clip distinct titles.
            clip_keywords = seo.extract_keywords(clip["text"], info["title"])
            clip_seo = seo.generate_seo(clip["text"], info["title"],
                                        clip_keywords, mode=mode)
            # Branded thumbnail (frame from the clip's midpoint, no burned
            # captions). A thumbnail failure must not fail the clip.
            thumb_url = None
            try:
                thumb_path = clips_dir / f"clip_{i + 1}.jpg"
                mid = (clip["start"] + clip["end"]) / 2
                thumbnails.make_thumbnail(video_path, mid, thumb_path,
                                          clip_seo["titles"][0])
                thumb_url = f"/api/jobs/{job_id}/clips/{i + 1}/thumbnail"
            except Exception as exc:  # noqa: BLE001 - thumbnail is optional
                print(f"thumbnail failed for clip {i + 1}: {exc}")
            clips.append({
                "n": i + 1,
                "start": clip["start"],
                "end": clip["end"],
                "duration": clip["duration"],
                "score": clip["score"],
                "reason": clip["reason"],
                "text": clip["text"],
                "seo": clip_seo,
                "download_url": f"/api/jobs/{job_id}/clips/{i + 1}/download",
                "thumbnail_url": thumb_url,
            })
            store.set_clips(db_path, job_id, clips)

        progress(100, "Done", status="done")
    except Exception as exc:  # noqa: BLE001 - surface any failure on the job
        traceback.print_exc()
        store.update_job(db_path, job_id, status="failed", error=str(exc),
                         message="Failed")
