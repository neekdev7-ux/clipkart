"""Background pipeline: info -> download -> transcribe -> score ->
cut+caption -> SEO. Updates the job row as it goes.
"""
from __future__ import annotations

import traceback
from pathlib import Path

from ..pipeline import captions, cut, download, score, seo, transcribe
from . import store


def run_pipeline(db_path, job_root, job_id):
    job_dir = Path(job_root) / job_id
    clips_dir = job_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    def progress(pct, message, status="processing"):
        store.update_job(db_path, job_id, progress=pct, message=message,
                         status=status)

    try:
        job = store.get_job(db_path, job_id)
        url = job["url"]
        max_clips = job["max_clips"]
        clip_seconds = job["clip_seconds"]

        progress(5, "Fetching video info...")
        info = download.get_video_info(url)
        store.update_job(db_path, job_id, title=info["title"],
                         thumbnail=info["thumbnail"],
                         duration=info["duration"])

        progress(20, "Downloading video...")
        video_path = download.download_video(url, job_dir / "video.mp4")

        progress(45, "Transcribing audio (Whisper)...")
        result = transcribe.transcribe(video_path, work_dir=job_dir)
        words = result["words"]
        if len(words) < 20:
            raise RuntimeError("Transcript too short — is there speech in this video?")
        energy = score.compute_energy_profile(result["wav_path"])

        progress(65, "Finding viral moments...")
        ranked = score.rank_clips(words, title=info["title"],
                                  clip_seconds=clip_seconds,
                                  max_clips=max_clips, energy=energy)
        if not ranked:
            raise RuntimeError("Video too short to cut 30s clips from.")

        keywords = seo.extract_keywords(" ".join(w["word"] for w in words),
                                        info["title"])
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
            clip_seo = seo.generate_seo(clip["text"], info["title"], keywords)
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
            })
            store.set_clips(db_path, job_id, clips)

        progress(100, "Done", status="done")
    except Exception as exc:  # noqa: BLE001 - surface any failure on the job
        traceback.print_exc()
        store.update_job(db_path, job_id, status="failed", error=str(exc),
                         message="Failed")
