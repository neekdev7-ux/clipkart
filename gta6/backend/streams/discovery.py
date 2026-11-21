"""Find live GTA 6 streams on YouTube.

Two sources, in priority order:
1. YouTube Data API v3 search (eventType=live) when YOUTUBE_API_KEY is set.
2. yt-dlp search (no key needed) — filters entries with is_live.

Both return the same shape: a list of dicts
{video_id, url, title, channel, viewers, thumbnail}.
"""
from __future__ import annotations

import re


def _clean_stream(video_id, title, channel, viewers, thumbnail=""):
    return {
        "video_id": video_id or "",
        "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
        "title": title or "",
        "channel": channel or "",
        "viewers": int(viewers or 0),
        "thumbnail": thumbnail or "",
    }


# ---------------------------------------------------------------------------
# YouTube Data API v3 (needs an API key; costs ~100 quota units per search
# plus 1 unit per videos.list call — cheap next to uploads at 1600 each)
# ---------------------------------------------------------------------------

def _search_via_api(query, api_key, max_results=10):
    from googleapiclient.discovery import build

    yt = build("youtube", "v3", developerKey=api_key)
    resp = yt.search().list(
        part="snippet", q=query, type="video", eventType="live",
        maxResults=max_results, order="viewCount").execute()
    ids = [item["id"]["videoId"] for item in resp.get("items", [])
           if item.get("id", {}).get("videoId")]
    if not ids:
        return []
    details = yt.videos().list(
        part="snippet,liveStreamingDetails",
        id=",".join(ids)).execute()
    out = []
    for item in details.get("items", []):
        live = item.get("liveStreamingDetails", {})
        if "actualEndTime" in live:
            continue  # stream already ended
        viewers = live.get("concurrentViewers")
        out.append(_clean_stream(
            item["id"], item["snippet"].get("title", ""),
            item["snippet"].get("channelTitle", ""),
            int(viewers) if viewers else 0,
            item["snippet"].get("thumbnails", {}).get("medium", {}).get("url", "")))
    return out


# ---------------------------------------------------------------------------
# yt-dlp search (no key; uses the public search pages)
# ---------------------------------------------------------------------------

def _search_via_ytdlp(query, max_results=10):
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "noplaylist": True,
            "extract_flat": True}
    out = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{max_results}:{query}",
                                download=False)
    for entry in (info.get("entries") or []):
        if not entry:
            continue
        # Flat search results may not carry is_live; check what we have.
        if entry.get("is_live") is False:
            continue
        if entry.get("live_status") in ("not_live", "is_upcoming"):
            continue
        out.append(_clean_stream(
            entry.get("id", ""), entry.get("title", ""),
            entry.get("uploader") or entry.get("channel") or "",
            entry.get("view_count") or 0,
            (entry.get("thumbnails") or [{}])[-1].get("url", "")
            if entry.get("thumbnails") else ""))
    return out


def search_live_streams(query, api_key=None, max_results=10):
    """Search one query for live streams. API first, yt-dlp fallback."""
    if api_key:
        try:
            return _search_via_api(query, api_key, max_results)
        except Exception:
            pass  # fall through to yt-dlp
    return _search_via_ytdlp(query, max_results)


def discover_live_streams(queries, api_key=None, min_viewers=10,
                          max_results_per_query=5):
    """Run all queries, dedupe by video id, filter by min viewers.

    Returns streams sorted by viewers desc.
    """
    seen = {}
    for query in queries:
        try:
            results = search_live_streams(query, api_key=api_key,
                                          max_results=max_results_per_query)
        except Exception:
            continue
        for s in results:
            if not s["video_id"] or s["video_id"] in seen:
                continue
            if s["viewers"] and s["viewers"] < min_viewers:
                continue
            seen[s["video_id"]] = s
    return sorted(seen.values(), key=lambda s: s["viewers"], reverse=True)


def get_stream_info(url: str) -> dict:
    """Full info for one stream URL, including is_live + HLS manifest URL.

    Returns {video_id, title, channel, viewers, thumbnail, is_live,
    hls_url}. hls_url is "" when no HLS format is available.
    """
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    hls_url = ""
    candidates = []
    for fmt in info.get("formats") or []:
        furl = fmt.get("url", "")
        proto = fmt.get("protocol", "")
        if proto in ("m3u8", "m3u8_native") or furl.endswith(".m3u8"):
            candidates.append(fmt)
    # Prefer a combined audio+video HLS variant: the first m3u8 format
    # yt-dlp lists is often audio-only, which records sound with no
    # picture (no Short can be cut from it). Pick the smallest height
    # >= 480p to keep recordings light; fall back to the largest
    # available A/V variant, then to any HLS variant.
    av = [f for f in candidates
          if f.get("vcodec") not in (None, "none")
          and f.get("acodec") not in (None, "none")]

    def _height(f):
        return f.get("height") or 0

    if av:
        ge480 = [f for f in av if _height(f) >= 480]
        if ge480:
            best = min(ge480, key=_height)
        else:
            best = max(av, key=_height)
        hls_url = best.get("url", "")
    elif candidates:
        hls_url = candidates[0].get("url", "")
    if not hls_url:
        hls_url = info.get("url", "") or ""
    stream = _clean_stream(
        info.get("id", ""), info.get("title", ""),
        info.get("uploader") or info.get("channel") or "",
        info.get("view_count") or info.get("concurrent_view_count") or 0,
        info.get("thumbnail", ""))
    stream["is_live"] = bool(info.get("is_live"))
    stream["hls_url"] = hls_url
    return stream


def extract_video_id(url: str) -> str:
    m = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", url or "")
    if m:
        return m.group(1)
    m = re.search(r"youtu\.be/([A-Za-z0-9_-]{11})", url or "")
    if m:
        return m.group(1)
    m = re.search(r"/live/([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else ""
