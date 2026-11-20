"""Virality scoring for transcript windows.

Splits a word-level transcript into sentence-aligned windows of 30-60s,
scores each 0-100 on hook strength, title overlap, audio energy,
completeness and emotion/story words, and returns the top N windows
with a one-line reason each.

No ML model is needed here: scoring is rule-based and fully testable.
"""
from __future__ import annotations

import math
import re
import wave

# ---------------------------------------------------------------------------
# Lexicons (English + Hindi/Hinglish, since the target audience is bilingual)
# ---------------------------------------------------------------------------

POWER_WORDS = {
    # English
    "secret", "mistake", "free", "never", "how", "why", "truth", "hack",
    "nobody", "stop", "warning", "shocking", "insane", "crazy", "proven",
    "easy", "fast", "best", "worst", "huge", "amazing", "incredible",
    "exactly", "finally", "actually", "everyone", "nobody", "always",
    "guaranteed", "hidden", "real", "exposed", "broke", "rich",
    # Hindi / Hinglish
    "raaz", "galti", "muft", "kabhi", "kaise", "kyu", "sach", "tareeka",
    "band", "chamatkar", "sabse", "asli", "chhupa", "zaroor", "paise",
    "kamao", "aasan", "tez",
}

EMOTION_WORDS = {
    # English
    "love", "hate", "fear", "scared", "angry", "happy", "sad", "cry",
    "laugh", "shocking", "unbelievable", "wow", "omg", "amazing",
    "incredible", "terrible", "horrible", "beautiful", "story", "remember",
    "imagine", "dream", "nightmare", "dead", "died", "killed", "saved",
    "lost", "found", "won", "failed", "success", "pain", "hurt",
    # Hindi / Hinglish
    "kahani", "darr", "khushi", "dukh", "pyaar", "gussa", "sapna",
    "yaad", "maza", "dard", "jeet", "haar", "kahaani", "bhoot",
}

QUESTION_WORDS = {
    "what", "why", "how", "when", "where", "who", "which", "did", "do",
    "does", "is", "are", "can", "could", "should", "kya", "kaise", "kyu",
    "kab", "kahan", "kaun",
}

STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "have", "has",
    "are", "was", "were", "will", "would", "can", "could", "should",
    "you", "your", "they", "them", "their", "our", "its", "it's", "but",
    "not", "all", "any", "had", "her", "his", "one", "two", "about",
    "into", "than", "then", "there", "when", "what", "which", "who",
    "them", "then", "also", "more", "very", "just", "like", "get",
    "got", "going", "know", "think", "really", "much", "many", "some",
    "hai", "hain", "ka", "ki", "ke", "ko", "se", "mein", "me", "aur",
    "yeh", "woh", "jo", "toh", "bhi", "nahi", "kya", "hai", "tha",
    "thi", "the", "kar", "karke", "raha", "rahi", "rahe", "aap", "hum",
    "is", "in", "on", "at", "to", "of", "a", "an", "is", "it", "as",
}

_SENTENCE_END = re.compile(r"[.!?…]+$")
_NUMBER = re.compile(r"\d")


def _clean(word: str) -> str:
    return re.sub(r"[^a-z0-9\u0900-\u097f]", "", word.lower())


# ---------------------------------------------------------------------------
# Windowing
# ---------------------------------------------------------------------------

def sentence_spans(words):
    """Split words into sentence spans: list of (start_idx, end_idx_exclusive)."""
    spans = []
    start = 0
    for i, w in enumerate(words):
        text = w["word"].strip()
        if _SENTENCE_END.search(text) or (i - start) >= 40:
            spans.append((start, i + 1))
            start = i + 1
    if start < len(words):
        spans.append((start, len(words)))
    return spans


def build_windows(words, clip_seconds=45, step_seconds=15,
                  min_seconds=30, max_seconds=60):
    """Build sentence-aligned candidate windows.

    Each window starts at a sentence boundary and extends (whole sentences)
    until it covers ~clip_seconds, capped at max_seconds. The next window
    starts at the first sentence beginning >= step_seconds later.
    Returns list of dicts: {start, end, start_idx, end_idx, text}.
    """
    if not words:
        return []
    spans = sentence_spans(words)
    if not spans:
        return []

    # Sentence start times for stepping.
    sent_starts = [words[s][ "start"] for s, _ in spans]
    windows = []
    i = 0
    total_end = words[-1]["end"]
    while i < len(spans):
        start_idx = spans[i][0]
        start_t = words[start_idx]["start"]
        # Extend whole sentences until we reach clip_seconds (or the cap).
        j = i
        end_t = words[spans[j][1] - 1]["end"]
        while j + 1 < len(spans) and end_t - start_t < clip_seconds:
            next_end = words[spans[j + 1][1] - 1]["end"]
            if next_end - start_t > max_seconds:
                break
            j += 1
            end_t = next_end
        duration = end_t - start_t
        if duration >= min_seconds:
            end_idx = spans[j][1]
            text = " ".join(w["word"] for w in words[start_idx:end_idx])
            windows.append({
                "start": round(start_t, 2),
                "end": round(end_t, 2),
                "start_idx": start_idx,
                "end_idx": end_idx,
                "text": text.strip(),
                "complete": True,
            })
        # Step forward ~step_seconds.
        target = start_t + step_seconds
        next_i = i + 1
        while next_i < len(spans) and sent_starts[next_i] < target:
            next_i += 1
        if next_i == i:
            next_i = i + 1
        i = next_i
        if i < len(spans) and total_end - sent_starts[i] < min_seconds:
            break
    return windows


# ---------------------------------------------------------------------------
# Audio energy (RMS per 1-second bucket from a 16kHz mono wav)
# ---------------------------------------------------------------------------

def compute_energy_profile(wav_path, bucket_seconds=1.0):
    """Return list of RMS values, one per bucket. None if unavailable."""
    try:
        import numpy as np
    except ImportError:
        return None
    try:
        with wave.open(str(wav_path), "rb") as wf:
            rate = wf.getframerate()
            channels = wf.getnchannels()
            width = wf.getsampwidth()
            frames = wf.readframes(wf.getnframes())
        if width != 2:
            return None
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1)
        per_bucket = max(1, int(rate * bucket_seconds))
        n = len(audio) // per_bucket
        if n == 0:
            return None
        trimmed = audio[: n * per_bucket].reshape(n, per_bucket)
        rms = np.sqrt((trimmed ** 2).mean(axis=1))
        return [float(x) for x in rms]
    except Exception:
        return None


def _energy_score(start, end, energy):
    """0-20: louder-than-average windows score higher. Neutral 10 if no data."""
    if not energy:
        return 10.0
    mean_all = sum(energy) / len(energy)
    if mean_all <= 0:
        return 10.0
    lo = max(0, int(math.floor(start)))
    hi = min(len(energy), max(lo + 1, int(math.ceil(end))))
    mean_win = sum(energy[lo:hi]) / max(1, hi - lo)
    ratio = mean_win / mean_all
    return round(max(0.0, min(20.0, 20.0 * ratio / 1.5)), 1)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _hook_score(window_words):
    """0-30 from the first 5 seconds of the window."""
    if not window_words:
        return 0.0
    t0 = window_words[0]["start"]
    first = [w for w in window_words if w["start"] - t0 <= 5.0]
    if not first:
        first = window_words[:8]
    text = " ".join(w["word"] for w in first)
    clean = [_clean(w["word"]) for w in first]
    score = 0.0
    if "?" in text:
        score += 10
    if _NUMBER.search(text):
        score += 6
    power_hits = sum(1 for c in clean if c in POWER_WORDS)
    score += min(12.0, power_hits * 4.0)
    if clean and clean[0] in QUESTION_WORDS:
        score += 2
    return min(30.0, score)


def _title_overlap_score(text, title):
    """0-20 from keyword overlap with the video title."""
    if not title:
        return 0.0
    title_words = {_clean(w) for w in title.split()}
    title_words = {w for w in title_words if len(w) > 2 and w not in STOPWORDS}
    if not title_words:
        return 0.0
    text_words = {_clean(w) for w in text.split()}
    overlap = len(title_words & text_words) / len(title_words)
    return round(20.0 * overlap, 1)


def _emotion_score(text):
    """0-15 from emotion/story word density."""
    words = [_clean(w) for w in text.split()]
    hits = sum(1 for w in words if w in EMOTION_WORDS)
    return min(15.0, hits * 3.0)


def score_window(window, words, title="", energy=None):
    """Score one window 0-100. Returns (score, reason)."""
    w_words = words[window["start_idx"]:window["end_idx"]]
    text = window["text"]
    hook = _hook_score(w_words)
    overlap = _title_overlap_score(text, title)
    energy_s = _energy_score(window["start"], window["end"], energy)
    complete = 15.0 if window.get("complete") else 8.0
    emotion = _emotion_score(text)
    total = round(min(100.0, hook + overlap + energy_s + complete + emotion), 1)

    parts = []
    if hook >= 14:
        parts.append("Strong hook")
    elif hook >= 8:
        parts.append("Good hook")
    if energy_s >= 15:
        parts.append("high energy")
    if overlap >= 12:
        parts.append("matches title")
    if emotion >= 9:
        parts.append("emotional peak")
    if not parts:
        parts.append("complete story beat")
    reason = parts[0] + (" + " + " + ".join(parts[1:]) if len(parts) > 1 else "")
    return total, reason


def _overlap_ratio(a, b):
    """Fraction of the shorter window covered by their overlap."""
    overlap = max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
    shorter = min(a["end"] - a["start"], b["end"] - b["start"])
    return overlap / shorter if shorter > 0 else 0.0


def rank_clips(words, title="", clip_seconds=45, max_clips=5, energy=None):
    """Return the top max_clips windows, deduplicated, sorted by score desc.

    Each item: {start, end, duration, score, reason, text}.
    """
    windows = build_windows(words, clip_seconds=clip_seconds)
    scored = []
    for w in windows:
        score, reason = score_window(w, words, title=title, energy=energy)
        scored.append({
            "start": w["start"],
            "end": w["end"],
            "duration": round(w["end"] - w["start"], 1),
            "score": score,
            "reason": reason,
            "text": w["text"],
        })
    scored.sort(key=lambda c: c["score"], reverse=True)
    picked = []
    for cand in scored:
        if len(picked) >= max_clips:
            break
        if any(_overlap_ratio(cand, p) > 0.3 for p in picked):
            continue
        picked.append(cand)
    return picked
