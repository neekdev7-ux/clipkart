"""Always-on monitor worker (asyncio task + worker threads).

Loop:
1. Discover live GTA 6 streams (yt-dlp search, or YouTube Data API
   when a key is set) and add new ones to the watchlist.
2. Start a recorder per watched stream (up to MAX_WATCHED_STREAMS).
3. When a segment finishes, process it (transcribe -> GTA 6 score ->
   cut -> SEO) and queue detected clips.
4. If AUTO_UPLOAD is on and a valid OAuth token exists, upload
   detected clips automatically (quota-guarded). Otherwise clips wait
   for manual approval in the dashboard.
5. Prune old segments (retention + disk cap).

Start/stop via the API; state() reports everything the dashboard needs.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
import traceback
import uuid
from pathlib import Path

from ..streams import chat as chat_mod
from ..streams import discovery, recorder as recorder_mod
from . import segment_processor, store


class Monitor:
    def __init__(self, settings, uploader=None):
        self.settings = settings
        self.uploader = uploader  # set by main.py (lazy, avoids import cycles)
        self.db_path = settings.db_path
        self.running = False
        self.task = None
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="clipnova-segment")
        self._recorders = {}   # stream_id -> StreamRecorder
        self._chat = {}        # stream_id -> ChatSpikeDetector
        self._processed_segments = set()
        self._lock = threading.Lock()
        self.last_discovery = None
        self.last_error = ""
        self.started_at = None
        self.stats = {"discovered": 0, "recorded": 0, "clips": 0,
                      "uploaded": 0}

    # -- lifecycle -----------------------------------------------------------

    async def start(self):
        if self.running:
            return False
        self.running = True
        self.started_at = time.time()
        self.task = asyncio.create_task(self._loop())
        return True

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        for rec in list(self._recorders.values()):
            rec.stop()
        for det in list(self._chat.values()):
            det.stop()
        self._recorders.clear()
        self._chat.clear()
        return True

    def state(self) -> dict:
        streams = store.list_streams(self.db_path)
        return {
            "running": self.running,
            "started_at": self.started_at,
            "last_discovery": self.last_discovery,
            "last_error": self.last_error,
            "stats": dict(self.stats),
            "auto_upload": self.settings.auto_upload,
            "queries": self.settings.queries,
            "watched": [
                {"id": s["id"], "video_id": s["video_id"],
                 "title": s["title"], "channel": s["channel"],
                 "viewers": s["viewers"], "status": s["status"]}
                for s in streams if s["status"] in ("watching", "recording")
            ],
            "disk_bytes": recorder_mod.dir_size_bytes(
                self.settings.stream_root),
            "disk_cap_bytes": int(self.settings.disk_cap_gb * 1024 ** 3),
        }

    # -- main loop -------------------------------------------------------------

    async def _loop(self):
        while self.running:
            try:
                await asyncio.to_thread(self._tick)
            except Exception:  # noqa: BLE001 - monitor must not die on errors
                traceback.print_exc()
                self.last_error = "tick failed (see server log)"
            await asyncio.sleep(self.settings.discovery_interval_seconds)

    def _tick(self):
        self._discover()
        self._manage_recorders()
        self._process_new_segments()
        self._auto_upload_pending()
        self._prune()

    def _discover(self):
        found = discovery.discover_live_streams(
            self.settings.queries,
            api_key=self.settings.youtube_api_key or None,
            min_viewers=self.settings.min_viewers)
        self.last_discovery = time.time()
        for s in found:
            if store.get_stream_by_video_id(self.db_path, s["video_id"]):
                continue
            stream_id = uuid.uuid4().hex[:12]
            store.create_stream(
                self.db_path, stream_id, s["video_id"], s["url"],
                title=s["title"], channel=s["channel"], viewers=s["viewers"],
                segments_dir=str(self.settings.stream_root / s["video_id"]))
            self.stats["discovered"] += 1

    def _manage_recorders(self):
        watching = [s for s in store.list_streams(self.db_path)
                    if s["status"] in ("watching", "recording")]
        active = len([r for r in self._recorders.values()
                      if r.status == "recording"])
        for s in watching:
            rec = self._recorders.get(s["id"])
            if rec is not None:
                if rec.status == "ended":
                    store.update_stream(self.db_path, s["id"], status="ended",
                                        error=rec.error)
                    self._recorders.pop(s["id"], None)
                    det = self._chat.pop(s["id"], None)
                    if det:
                        det.stop()
                continue
            if active >= self.settings.max_watched_streams:
                continue
            try:
                info = discovery.get_stream_info(s["url"])
            except Exception as exc:  # noqa: BLE001 - keep watching, retry later
                store.update_stream(self.db_path, s["id"], error=str(exc)[:200])
                continue
            if not info.get("is_live"):
                store.update_stream(self.db_path, s["id"], status="ended")
                continue
            rec = recorder_mod.StreamRecorder(
                s["video_id"], info["hls_url"], s["segments_dir"] or
                str(self.settings.stream_root / s["video_id"]),
                segment_minutes=self.settings.segment_minutes)
            if rec.start():
                self._recorders[s["id"]] = rec
                store.update_stream(self.db_path, s["id"], status="recording",
                                    viewers=info.get("viewers", 0))
                active += 1
                self.stats["recorded"] += 1
                self._start_chat(s)
            else:
                store.update_stream(self.db_path, s["id"], error=rec.error)

    def _start_chat(self, stream):
        """Chat spike detection is optional and best-effort."""
        try:
            creds = None
            if self.uploader is not None and self.uploader.is_authorized():
                creds = self.uploader.get_credentials()
            det = chat_mod.make_detector(stream["video_id"], credentials=creds)
            if det.start():
                self._chat[stream["id"]] = det
        except Exception:  # noqa: BLE001 - chat must never break the monitor
            pass

    def _process_new_segments(self):
        for stream_id, rec in list(self._recorders.items()):
            stream = store.get_stream(self.db_path, stream_id)
            if not stream:
                continue
            det = self._chat.get(stream_id)
            chat_fn = (lambda a, b, d=det: d.spike_bonus(a, b)) if det else None
            for seg in rec.completed_segments():
                key = str(seg)
                if key in self._processed_segments:
                    continue
                self._processed_segments.add(key)
                offset = self._segment_offset(seg)
                future = self._executor.submit(
                    segment_processor.process_segment,
                    self.db_path, self.settings.clip_root, stream, seg,
                    segment_offset=offset, chat_fn=chat_fn,
                    settings=self.settings)
                future.add_done_callback(self._on_segment_done)

    def _segment_offset(self, segment_path) -> float:
        """Seconds from stream start to this segment (best effort: parse
        the sequence number from the filename)."""
        try:
            seq = int(Path(segment_path).stem.rsplit("_", 1)[1])
            return float(seq) * self.settings.segment_minutes * 60.0
        except (ValueError, IndexError):
            return 0.0

    def _on_segment_done(self, future):
        try:
            clips = future.result() or []
            self.stats["clips"] += len(clips)
        except Exception:  # noqa: BLE001 - logged by the processor already
            pass

    def _auto_upload_pending(self):
        if not self.settings.auto_upload or self.uploader is None:
            return
        pending = store.list_clips(self.db_path, status="detected")
        for clip in pending:
            try:
                allowed, _ = self.uploader.can_upload(self.db_path)
                if not allowed:
                    return  # quota/auth exhausted; try again next tick
                self.uploader.upload_clip(
                    self.db_path, clip, clip["file_path"])
                self.stats["uploaded"] += 1
            except Exception:  # noqa: BLE001 - logged in uploads table
                continue

    def _prune(self):
        root = self.settings.stream_root
        if not root.exists():
            return
        for stream_dir in root.iterdir():
            if stream_dir.is_dir():
                recorder_mod.prune_segments(
                    stream_dir,
                    retention_hours=self.settings.retention_hours,
                    disk_cap_gb=self.settings.disk_cap_gb)
