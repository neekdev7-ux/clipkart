"""GTA 6 hype scoring, layered on top of the base ClipNova scorer.

Base score (hook, title overlap, audio energy, completeness, emotion)
+ GTA 6 lexicon bonus (Vice City, Lucia, leaks, heists, ...) + an
optional live-chat spike bonus. Output is still 0-100 with a reason
line, so the rest of the pipeline is unchanged.
"""
from __future__ import annotations

import re

from ..pipeline import score as base_score

# Single-word hype terms (matched on cleaned words).
GTA6_WORDS = {
    # Game / world
    "leonida", "lucia", "jason", "vice", "rockstar", "heist", "wanted",
    "gameplay", "trailer", "leak", "leaked", "reveal", "revealed", "map",
    "trailer2", "gta", "gtavi", "vi", "vicecity",
    # Moments
    "chase", "police", "cops", "shootout", "explosion", "crash", "stunt",
    "race", "getaway", "robbery", "mission", "boss", "easter", "secret",
    # Reaction words
    "insane", "crazy", "unreal", "mind-blowing", "goat", "banger",
    # Hindi / Hinglish hype
    "bhai", "dekh", "pagal", "mast", "khatarnak", "gazab", "dhansu",
    "faad", "op", "scene",
}

# Multi-word phrases (matched on the lowercased text).
GTA6_PHRASES = {
    "vice city", "gta 6", "gta vi", "grand theft auto", "first look",
    "police chase", "new feature", "map leak", "trailer 2", "trailer two",
    "release date", "pre order", "pre-order", "open world", "leonida keys",
    "ocean drive", "what just happened", "did you see",
}

MAX_HYPE_BONUS = 20.0
MAX_CHAT_BONUS = 15.0


def _clean(word: str) -> str:
    return re.sub(r"[^a-z0-9\u0900-\u097f]", "", word.lower())


def hype_hits(text: str) -> list:
    """GTA 6 lexicon hits in text (words + phrases), lowercased."""
    lowered = (text or "").lower()
    hits = []
    for phrase in GTA6_PHRASES:
        if phrase in lowered:
            hits.append(phrase)
    for w in re.findall(r"[a-z0-9\u0900-\u097f]+", lowered):
        if w in GTA6_WORDS:
            hits.append(w)
    return hits


def hype_bonus(text: str) -> float:
    """0-20: 4 points per distinct hype hit, capped."""
    distinct = set(hype_hits(text))
    return min(MAX_HYPE_BONUS, len(distinct) * 4.0)


def _gta_hook_bonus(window_words) -> float:
    """0-15: the base hook scorer is English-centric and misses
    Hinglish/GTA 6 openers ("Bhai dekh, Vice City ka trailer leak...").
    Reward GTA 6 lexicon hits in the first 5 seconds directly."""
    if not window_words:
        return 0.0
    t0 = window_words[0]["start"]
    first = [w for w in window_words if w["start"] - t0 <= 5.0]
    if not first:
        first = window_words[:8]
    text = " ".join(w["word"] for w in first)
    hits = set(hype_hits(text))
    return min(15.0, len(hits) * 5.0)


def score_window_gta6(window, words, title="", energy=None, chat_bonus=0.0):
    """Score one window 0-100 with GTA 6 hype + hook + chat bonuses.

    Returns (score, reason). `chat_bonus` is 0..15 from the chat
    spike detector for this window (0 when chat is unavailable).
    """
    base, reason = base_score.score_window(window, words, title=title,
                                           energy=energy)
    w_words = words[window["start_idx"]:window["end_idx"]]
    hype = hype_bonus(window["text"])
    hook = _gta_hook_bonus(w_words)
    chat = max(0.0, min(MAX_CHAT_BONUS, float(chat_bonus or 0.0)))
    total = round(min(100.0, base + hype + hook + chat), 1)

    parts = [reason]
    if hook >= 10:
        parts.append("GTA 6 hook")
    if hype >= 12:
        parts.append("GTA 6 hype peak")
    elif hype >= 4:
        parts.append("GTA 6 moment")
    if chat > 0:
        parts.append("chat spike")
    return total, " + ".join(parts)


def rank_clips_gta6(words, title="", clip_seconds=45, max_clips=5,
                    energy=None, chat_fn=None, min_score=0):
    """Top max_clips windows by GTA 6 score, deduplicated, score desc.

    chat_fn(start, end) -> 0..15 bonus, optional. Clips below min_score
    are dropped. Each item: {start, end, duration, score, reason, text}.
    """
    windows = base_score.build_windows(words, clip_seconds=clip_seconds)
    scored = []
    for w in windows:
        chat = chat_fn(w["start"], w["end"]) if chat_fn else 0.0
        s, reason = score_window_gta6(w, words, title=title, energy=energy,
                                      chat_bonus=chat)
        if s < min_score:
            continue
        scored.append({
            "start": w["start"],
            "end": w["end"],
            "duration": round(w["end"] - w["start"], 1),
            "score": s,
            "reason": reason,
            "text": w["text"],
        })
    scored.sort(key=lambda c: c["score"], reverse=True)
    picked = []
    for cand in scored:
        if len(picked) >= max_clips:
            break
        if any(base_score._overlap_ratio(cand, p) > 0.3 for p in picked):
            continue
        picked.append(cand)
    return picked
