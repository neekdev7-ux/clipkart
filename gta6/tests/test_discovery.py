"""discovery.get_stream_info must pick a combined A/V HLS variant.

Regression test: it used to take the first m3u8 format yt-dlp listed,
which for live streams is often audio-only — recordings then had sound
with no picture and no Short could be cut from them. yt-dlp is mocked;
no network.
"""
import yt_dlp

from backend.streams import discovery


class _FakeYDL:
    def __init__(self, info):
        self._info = info

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        return self._info


def _info(formats):
    return {"id": "vid1", "title": "T", "uploader": "C", "is_live": True,
            "formats": formats, "url": "https://example.com/fallback"}


def _fmt(url, vcodec, acodec, height):
    return {"url": url, "protocol": "m3u8", "vcodec": vcodec,
            "acodec": acodec, "height": height}


def test_prefers_combined_av_over_audio_only(monkeypatch):
    formats = [
        _fmt("https://example.com/audio.m3u8", "none", "mp4a", None),
        _fmt("https://example.com/av480.m3u8", "avc1", "mp4a", 480),
        _fmt("https://example.com/av720.m3u8", "avc1", "mp4a", 720),
    ]
    monkeypatch.setattr(yt_dlp, "YoutubeDL",
                        lambda opts: _FakeYDL(_info(formats)))
    stream = discovery.get_stream_info("https://www.youtube.com/watch?v=vid1")
    assert stream["hls_url"] == "https://example.com/av480.m3u8"


def test_prefers_largest_av_when_none_reaches_480(monkeypatch):
    formats = [
        _fmt("https://example.com/av144.m3u8", "avc1", "mp4a", 144),
        _fmt("https://example.com/av360.m3u8", "avc1", "mp4a", 360),
    ]
    monkeypatch.setattr(yt_dlp, "YoutubeDL",
                        lambda opts: _FakeYDL(_info(formats)))
    stream = discovery.get_stream_info("https://www.youtube.com/watch?v=vid1")
    assert stream["hls_url"] == "https://example.com/av360.m3u8"


def test_falls_back_to_first_hls_when_no_av(monkeypatch):
    formats = [_fmt("https://example.com/audio.m3u8", "none", "mp4a", None)]
    monkeypatch.setattr(yt_dlp, "YoutubeDL",
                        lambda opts: _FakeYDL(_info(formats)))
    stream = discovery.get_stream_info("https://www.youtube.com/watch?v=vid1")
    assert stream["hls_url"] == "https://example.com/audio.m3u8"


def test_falls_back_to_info_url_without_hls(monkeypatch):
    monkeypatch.setattr(yt_dlp, "YoutubeDL",
                        lambda opts: _FakeYDL(_info([])))
    stream = discovery.get_stream_info("https://www.youtube.com/watch?v=vid1")
    assert stream["hls_url"] == "https://example.com/fallback"
