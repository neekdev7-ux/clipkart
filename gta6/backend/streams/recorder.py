"""Record a live HLS stream in rolling segments with ffmpeg.

- One ffmpeg process per stream: `-f segment -segment_time N` writes
  fixed-length .mp4 files (stream copy, no re-encode).
- Rolling retention: segments older than RETENTION_HOURS are deleted,
  and the oldest are deleted first when the disk cap is exceeded.
- Stream end / disconnect: ffmpeg exits on its own; the recorder marks
  the stream ended and keeps the segments already on disk.

All file handling is pure stdlib so retention is fully unit-testable.
"""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

SEGMENT_GLOB = "seg_*.mp4"


def segment_files(segments_dir) -> list:
    """Segment files sorted oldest-first (by filename, which is time-ordered)."""
    d = Path(segments_dir)
    if not d.exists():
        return []
    return sorted(d.glob(SEGMENT_GLOB), key=lambda p: p.name)


def dir_size_bytes(segments_dir) -> int:
    d = Path(segments_dir)
    if not d.exists():
        return 0
    return sum(p.stat().st_size for p in d.rglob("*") if p.is_file())


def prune_segments(segments_dir, retention_hours=2.0, disk_cap_gb=20.0,
                   keep_newest=1) -> list:
    """Delete segments older than retention, then oldest-first past the cap.

    Always keeps at least `keep_newest` segments (the one ffmpeg is
    currently writing must never be deleted). Returns deleted paths.
    """
    files = segment_files(segments_dir)
    if not files:
        return []
    now = time.time()
    cutoff = now - retention_hours * 3600
    deleted = []

    def _drop(path):
        try:
            path.unlink()
            deleted.append(path)
        except OSError:
            pass

    # 1) Age-based retention (never touch the newest file).
    for path in files[:-keep_newest]:
        if path.stat().st_mtime < cutoff:
            _drop(path)

    # 2) Disk cap: oldest first until under the cap.
    remaining = [p for p in segment_files(segments_dir)]
    cap_bytes = disk_cap_gb * 1024 ** 3
    total = sum(p.stat().st_size for p in remaining)
    idx = 0
    while total > cap_bytes and len(remaining) - idx > keep_newest:
        victim = remaining[idx]
        idx += 1
        total -= victim.stat().st_size
        _drop(victim)
    return deleted


def build_ffmpeg_command(hls_url, segments_dir, segment_seconds=300,
                         audio_hls_url=""):
    """ffmpeg segmenting command (stream copy, keyframe-aligned cuts).

    When audio_hls_url is given (separate audio rendition), both inputs
    are mapped into the segments; otherwise the single input is copied
    as-is.
    """
    pattern = str(Path(segments_dir) / "seg_%Y%m%dT%H%M%S_%03d.mp4")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    for url in [hls_url] + ([audio_hls_url] if audio_hls_url else []):
        cmd += ["-reconnect", "1", "-reconnect_streamed", "1",
                "-reconnect_delay_max", "5", "-i", url]
    if audio_hls_url:
        cmd += ["-map", "0:v", "-map", "1:a"]
    cmd += [
        "-c", "copy",
        "-f", "segment",
        "-segment_time", str(segment_seconds),
        "-segment_format", "mp4",
        "-reset_timestamps", "1",
        "-strftime", "1",
        pattern,
    ]
    return cmd


class StreamRecorder:
    """One live recording. Runs ffmpeg in a background thread."""

    def __init__(self, video_id, hls_url, segments_dir, segment_minutes=5,
                 audio_hls_url=""):
        self.video_id = video_id
        self.hls_url = hls_url
        self.audio_hls_url = audio_hls_url
        self.segments_dir = Path(segments_dir)
        self.segment_seconds = max(60, int(segment_minutes) * 60)
        self.proc = None
        self.thread = None
        self.started_at = None
        self.ended_at = None
        self.error = ""
        self._stop_requested = threading.Event()

    @property
    def status(self) -> str:
        if self.ended_at:
            return "ended"
        if self.proc is not None and self.proc.poll() is None:
            return "recording"
        if self.started_at:
            return "ended"
        return "idle"

    def start(self) -> bool:
        """Launch ffmpeg. Returns False if the process exits immediately."""
        self.segments_dir.mkdir(parents=True, exist_ok=True)
        cmd = build_ffmpeg_command(self.hls_url, self.segments_dir,
                                   self.segment_seconds,
                                   audio_hls_url=self.audio_hls_url)
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except FileNotFoundError:
            self.error = "ffmpeg not found on PATH"
            return False
        self.started_at = time.time()
        self.thread = threading.Thread(target=self._watch, daemon=True)
        self.thread.start()
        # Give ffmpeg a moment to fail fast (bad URL, dead stream).
        time.sleep(2)
        if self.proc.poll() is not None:
            err = (self.proc.stderr.read() or b"").decode(errors="replace")
            self.error = (err.strip().splitlines() or ["ffmpeg exited"]) [-1][:300]
            self.ended_at = time.time()
            return False
        return True

    def _watch(self):
        """Wait for ffmpeg; a natural exit means the stream ended."""
        if self.proc is None:
            return
        _, err = self.proc.communicate()
        self.ended_at = time.time()
        if self.proc.returncode not in (0, None) and not self._stop_requested.is_set():
            text = (err or b"").decode(errors="replace")
            last = (text.strip().splitlines() or ["stream ended"])[-1]
            self.error = last[:300]

    def stop(self):
        """Stop recording gracefully; segments already written are kept."""
        self._stop_requested.set()
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.ended_at = self.ended_at or time.time()

    def segments(self) -> list:
        return segment_files(self.segments_dir)

    def completed_segments(self, stable_seconds=5.0) -> list:
        """Segments ffmpeg has finished writing: all but the newest, and
        only files whose size has been stable (mtime older than
        stable_seconds). The newest file is still being written."""
        files = self.segments()
        if not files:
            return []
        now = time.time()
        done = [p for p in files[:-1]
                if now - p.stat().st_mtime >= stable_seconds]
        if self.status == "ended" and files:
            last = files[-1]
            if now - last.stat().st_mtime >= stable_seconds and last not in done:
                done.append(last)
        return done
