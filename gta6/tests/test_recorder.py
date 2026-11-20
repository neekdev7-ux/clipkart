"""Recorder: segment rotation deletes the oldest past retention and
past the disk cap; the newest segment is always kept."""
import os
import time

from backend.streams import recorder as rec


def _make_segment(path, size=1024, age_seconds=0):
    path.write_bytes(b"x" * size)
    old = time.time() - age_seconds
    os.utime(path, (old, old))


def test_prune_deletes_old_segments_but_keeps_newest(tmp_path):
    d = tmp_path / "segs"
    d.mkdir()
    _make_segment(d / "seg_20260101T100000_000.mp4", age_seconds=5 * 3600)
    _make_segment(d / "seg_20260101T100500_001.mp4", age_seconds=4 * 3600)
    _make_segment(d / "seg_20260101T101000_002.mp4", age_seconds=60)
    deleted = rec.prune_segments(d, retention_hours=2.0, disk_cap_gb=20.0)
    assert len(deleted) == 2
    remaining = rec.segment_files(d)
    assert len(remaining) == 1
    assert remaining[0].name == "seg_20260101T101000_002.mp4"


def test_prune_keeps_newest_even_when_old(tmp_path):
    d = tmp_path / "segs"
    d.mkdir()
    _make_segment(d / "seg_20260101T100000_000.mp4", age_seconds=9 * 3600)
    deleted = rec.prune_segments(d, retention_hours=2.0, disk_cap_gb=20.0)
    assert deleted == []  # the only (newest) segment is never deleted
    assert len(rec.segment_files(d)) == 1


def test_prune_enforces_disk_cap_oldest_first(tmp_path):
    d = tmp_path / "segs"
    d.mkdir()
    for i in range(5):
        _make_segment(d / f"seg_20260101T10100{i}_00{i}.mp4", size=1024)
    # 5KB total, cap ~2KB -> keep the newest 2 files.
    deleted = rec.prune_segments(d, retention_hours=24.0,
                                 disk_cap_gb=2 * 1024 / (1024 ** 3))
    assert len(deleted) == 3
    remaining = [p.name for p in rec.segment_files(d)]
    assert remaining == ["seg_20260101T101003_003.mp4",
                         "seg_20260101T101004_004.mp4"]


def test_prune_empty_dir_is_noop(tmp_path):
    assert rec.prune_segments(tmp_path / "missing") == []


def test_segment_files_sorted_oldest_first(tmp_path):
    d = tmp_path / "segs"
    d.mkdir()
    for name in ("seg_20260101T101000_002.mp4",
                 "seg_20260101T100000_000.mp4",
                 "seg_20260101T100500_001.mp4"):
        (d / name).write_bytes(b"x")
    names = [p.name for p in rec.segment_files(d)]
    assert names == sorted(names)


def test_build_ffmpeg_command():
    cmd = rec.build_ffmpeg_command("https://example.com/live.m3u8",
                                   "/tmp/segs", segment_seconds=300)
    assert cmd[0] == "ffmpeg"
    assert "https://example.com/live.m3u8" in cmd
    assert "-segment_time" in cmd
    assert cmd[cmd.index("-segment_time") + 1] == "300"
    assert "-f" in cmd and "segment" in cmd
    assert any(p.startswith("/tmp/segs/seg_") for p in cmd)


def test_dir_size_bytes(tmp_path):
    d = tmp_path / "segs"
    d.mkdir()
    (d / "a.mp4").write_bytes(b"x" * 100)
    (d / "b.mp4").write_bytes(b"x" * 50)
    assert rec.dir_size_bytes(d) == 150
    assert rec.dir_size_bytes(tmp_path / "missing") == 0
