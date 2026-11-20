"""End-to-end smoke test on an ffmpeg-generated 90s video.

Stub transcription (no Whisper model download), real scoring, real
caption generation, real ffmpeg cutting in both crop and blur modes.
"""
import subprocess

import pytest

from backend.pipeline import captions, cut, score
from tests.conftest import words_from_text
from tests.test_score import FILLER_TEXT, HOOK_TEXT


def _make_test_video(path):
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=90:size=1280x720:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=90",
        "-shortest", "-c:v", "libx264", "-preset", "veryfast",
        "-c:a", "aac", str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def test_full_pipeline_on_generated_video(tmp_path):
    video = tmp_path / "test.mp4"
    _make_test_video(video)
    assert video.exists()

    words = words_from_text((HOOK_TEXT * 2) + (FILLER_TEXT * 3))
    clips = score.rank_clips(words, title="Money Saving Tips",
                             clip_seconds=45, max_clips=3)
    assert clips, "expected at least one clip from the stub transcript"

    clip = clips[0]
    ass_path = tmp_path / "clip1.ass"
    captions.build_ass(words, clip["start"], clip["end"], ass_path)
    assert ass_path.exists()

    out = tmp_path / "clip1.mp4"
    cut.cut_clip(video, clip["start"], clip["end"], out,
                 mode="crop", captions_ass=ass_path)
    assert out.exists() and out.stat().st_size > 1000
    assert cut.probe_resolution(out) == (1080, 1920)
    assert abs(cut.probe_duration(out) - clip["duration"]) < 1.5

    # Blur mode: short segment, just verify the filter graph works.
    blur_out = tmp_path / "blur.mp4"
    cut.cut_clip(video, 5.0, 10.0, blur_out, mode="blur")
    assert blur_out.exists()
    assert cut.probe_resolution(blur_out) == (1080, 1920)
