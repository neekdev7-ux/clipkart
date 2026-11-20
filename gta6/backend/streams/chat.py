"""OPTIONAL live-chat velocity spike detection.

Polls YouTube Data API liveChatMessages for a stream and records when
chat messages-per-minute spike far above the running baseline. Spikes
mark moments the audience reacted to — a bonus signal for clip scoring.

This module is OFF unless an OAuth token with the youtube.readonly
scope exists. It NEVER fails the pipeline: any error disables it and
scoring continues without the chat bonus.
"""
from __future__ import annotations

import time
from collections import deque

# Messages-per-minute above this multiple of the baseline counts as a spike.
SPIKE_MULTIPLIER = 2.5
MIN_BASELINE_MESSAGES = 20


class ChatSpikeDetector:
    """Polls one stream's live chat in a background thread."""

    def __init__(self, video_id, credentials=None, poll_seconds=15):
        self.video_id = video_id
        self.credentials = credentials
        self.poll_seconds = max(10, poll_seconds)
        self.enabled = credentials is not None
        self.live_chat_id = None
        self.page_token = None
        self.spikes = []  # [{start, end, velocity}] in stream-relative seconds
        self._minute_counts = deque(maxlen=30)  # (minute_index, count)
        self._current_minute = None
        self._current_count = 0
        self._stream_started_at = time.time()
        self._thread = None
        self._stop = False
        self.error = ""

    # -- scoring interface -------------------------------------------------

    def spike_bonus(self, start, end, max_bonus=15.0) -> float:
        """Bonus 0..max_bonus for a window overlapping a recorded spike."""
        if not self.enabled or not self.spikes:
            return 0.0
        for spike in self.spikes:
            if start < spike["end"] and end > spike["start"]:
                return max_bonus
        return 0.0

    def record_minute(self, minute_index, count):
        """Feed one minute of chat volume (used by the poller and tests)."""
        self._minute_counts.append((minute_index, count))
        if len(self._minute_counts) < 3:
            return
        counts = [c for _, c in self._minute_counts]
        baseline = sum(counts[:-1]) / max(1, len(counts) - 1)
        if baseline * SPIKE_MULTIPLIER <= count and count >= MIN_BASELINE_MESSAGES:
            minute_start = minute_index * 60.0
            self.spikes.append({
                "start": minute_start,
                "end": minute_start + 60.0,
                "velocity": count,
            })

    # -- polling -----------------------------------------------------------

    def start(self):
        if not self.enabled:
            return False
        import threading
        self._stop = False
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop = True

    def _poll_loop(self):
        try:
            from googleapiclient.discovery import build
            yt = build("youtube", "v3", credentials=self.credentials)
            resp = yt.videos().list(
                part="liveStreamingDetails", id=self.video_id).execute()
            items = resp.get("items", [])
            if not items:
                return
            self.live_chat_id = items[0].get(
                "liveStreamingDetails", {}).get("activeLiveChatId")
            if not self.live_chat_id:
                return
            while not self._stop:
                self._poll_once(yt)
                time.sleep(self.poll_seconds)
        except Exception as exc:  # noqa: BLE001 - chat must never break scoring
            self.error = str(exc)[:200]
            self.enabled = False

    def _poll_once(self, yt):
        resp = yt.liveChatMessages().list(
            liveChatId=self.live_chat_id, part="snippet",
            pageToken=self.page_token, maxResults=200).execute()
        self.page_token = resp.get("nextPageToken")
        now_minute = int((time.time() - self._stream_started_at) // 60)
        count = len(resp.get("items", []))
        if now_minute != self._current_minute:
            if self._current_minute is not None:
                self.record_minute(self._current_minute, self._current_count)
            self._current_minute = now_minute
            self._current_count = count
        else:
            self._current_count += count


def make_detector(video_id, credentials=None):
    """Build a detector; returns a disabled one without credentials."""
    return ChatSpikeDetector(video_id, credentials=credentials)
