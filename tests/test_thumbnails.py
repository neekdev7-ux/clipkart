"""Tests for branded clip thumbnails."""
import subprocess

from backend.pipeline import thumbnails
from tests.test_pipeline_smoke import _make_test_video


def test_wrap_title_short():
    assert thumbnails.wrap_title("GTA 6 Leak") == ["GTA 6 Leak"]


def test_wrap_title_long():
    lines = thumbnails.wrap_title("Why GTA 6 Game Changes Everything Fast")
    assert 1 < len(lines) <= 3
    assert all(len(line) <= thumbnails.MAX_LINE_CHARS for line in lines)
    assert " ".join(lines) == "Why GTA 6 Game Changes Everything Fast"


def test_wrap_title_overflow_ellipsized():
    title = " ".join(["word"] * 30)
    lines = thumbnails.wrap_title(title)
    assert len(lines) == thumbnails.MAX_LINES
    assert lines[-1].endswith("...")


def test_make_thumbnail_produces_vertical_jpg(tmp_path):
    video = tmp_path / "test.mp4"
    _make_test_video(video)
    out = tmp_path / "thumb.jpg"
    thumbnails.make_thumbnail(video, 10.0, out,
                              "GTA 6 Leak: Vice City Map Revealed!")
    assert out.exists() and out.stat().st_size > 1000
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0",
         str(out)],
        check=True, capture_output=True, text=True)
    assert probe.stdout.strip() == "1080,1920"
