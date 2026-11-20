"""Process one finished stream segment into GTA 6 Shorts.

Transcribe (Whisper) -> GTA 6 hype score -> cut top clips (vertical,
karaoke captions) -> GTA 6 SEO -> save clip rows (status "detected").

Runs in a worker thread from the monitor; all heavy work (Whisper,
ffmpeg) is CPU-bound and sequential per segment by design.
"""
from __future__ import annotations

import traceback
import uuid
from pathlib import Path

from ..gta6 import scorer as gta6_scorer
from ..gta6 import seo as gta6_seo
from ..pipeline import captions, cut, score as base_score, transcribe
from . import store


def process_segment(db_path, clip_root, stream, segment_path,
                    segment_offset=0.0, chat_fn=None, settings=None):
    """Process one segment file. Returns the list of created clip dicts.

    stream: dict with id/title/url/channel. segment_offset: seconds from
    the stream start to this segment's start (for stream-relative times).
    chat_fn(start, end) -> 0..15 bonus, optional.
    """
    segment_path = Path(segment_path)
    min_score = (settings.clip_min_score if settings else 60)
    max_clips = (settings.max_clips_per_segment if settings else 2)
    clip_seconds = (settings.clip_seconds if settings else 45)
    created = []
    if not segment_path.exists():
        return created
    try:
        duration = cut.probe_duration(segment_path)
    except Exception:
        return created
    if duration < 40:
        return created  # too short to yield a 30s+ clip

    work_dir = Path(clip_root) / f"seg_{segment_path.stem}"
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = transcribe.transcribe(segment_path, work_dir=work_dir)
        words = result["words"]
        if len(words) < 20:
            return created
        energy = base_score.compute_energy_profile(result["wav_path"])
        ranked = gta6_scorer.rank_clips_gta6(
            words, title=stream.get("title", ""), clip_seconds=clip_seconds,
            max_clips=max_clips, energy=energy, chat_fn=chat_fn,
            min_score=min_score)
        for clip in ranked:
            clip_id = uuid.uuid4().hex[:12]
            out_path = Path(clip_root) / f"{clip_id}.mp4"
            ass_path = work_dir / f"{clip_id}.ass"
            captions.build_ass(words, clip["start"], clip["end"], ass_path)
            try:
                cut.cut_clip(segment_path, clip["start"], clip["end"],
                             out_path, mode="crop", captions_ass=ass_path)
            except Exception:
                cut.cut_clip(segment_path, clip["start"], clip["end"],
                             out_path, mode="crop")
            seo = gta6_seo.generate_gta6_seo(
                clip["text"], stream_title=stream.get("title", ""),
                stream_url=stream.get("url", ""),
                channel=stream.get("channel", ""))
            record = {
                "stream_id": stream.get("id", ""),
                "stream_title": stream.get("title", ""),
                "stream_url": stream.get("url", ""),
                "channel": stream.get("channel", ""),
                "segment_file": str(segment_path),
                "start": round(segment_offset + clip["start"], 2),
                "end": round(segment_offset + clip["end"], 2),
                "duration": clip["duration"],
                "score": clip["score"],
                "reason": clip["reason"],
                "text": clip["text"],
                "seo": seo,
                "file_path": str(out_path),
                "status": "detected",
            }
            store.create_clip(db_path, clip_id, **record)
            created.append({**record, "id": clip_id})
    except Exception:
        traceback.print_exc()
    return created
