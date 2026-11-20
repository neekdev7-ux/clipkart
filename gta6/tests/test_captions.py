"""ASS captions: valid timed Dialogue lines with karaoke tags."""
import re

from backend.pipeline import captions
from tests.conftest import words_from_text

TEXT = ("Hello world this is a test of the caption system. "
        "Each word should highlight as it is spoken aloud. "
        "The quick brown fox jumps over the lazy dog today.")


def test_format_ass_time():
    assert captions.format_ass_time(0) == "0:00:00.00"
    assert captions.format_ass_time(65.5) == "0:01:05.50"
    assert captions.format_ass_time(3661.23) == "1:01:01.23"


def test_build_ass_produces_valid_timed_lines(tmp_path):
    words = words_from_text(TEXT, word_seconds=0.4)
    out = tmp_path / "caps.ass"
    captions.build_ass(words, 0.0, 12.0, out)
    content = out.read_text(encoding="utf-8")
    assert "[Script Info]" in content
    assert "[V4+ Styles]" in content
    assert "[Events]" in content
    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content
    dialogues = [ln for ln in content.splitlines() if ln.startswith("Dialogue:")]
    assert len(dialogues) >= 3
    # Every line has karaoke tags and increasing, well-formed timestamps.
    prev_end = -1.0
    ts_re = re.compile(r"Dialogue: 0,(\d+:\d\d:\d\d\.\d\d),(\d+:\d\d:\d\d\.\d\d),")
    for ln in dialogues:
        m = ts_re.match(ln)
        assert m, f"bad timestamp line: {ln}"
        assert "\\k" in ln, f"missing karaoke tag: {ln}"
        def _to_sec(ts):
            h, mi, s = ts.split(":")
            return int(h) * 3600 + int(mi) * 60 + float(s)
        start, end = _to_sec(m.group(1)), _to_sec(m.group(2))
        assert 0 <= start < end <= 12.0
        assert start >= prev_end - 0.01
        prev_end = end


def test_build_ass_clips_to_window(tmp_path):
    words = words_from_text(TEXT, word_seconds=0.4)
    out = tmp_path / "caps.ass"
    captions.build_ass(words, 4.0, 8.0, out)
    content = out.read_text(encoding="utf-8")
    dialogues = [ln for ln in content.splitlines() if ln.startswith("Dialogue:")]
    assert dialogues
    # First line starts at ~0 relative to the clip window.
    assert dialogues[0].split(",")[1] == "0:00:00.00"
