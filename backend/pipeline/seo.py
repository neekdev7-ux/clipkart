"""SEO generation for clips: titles, description, hashtags, tags.

Rule-based by default — no API key required. If GEMINI_API_KEY or
OPENAI_API_KEY is set, titles are optionally upgraded via that API,
with the rule-based output as a fallback on any failure.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

from .score import STOPWORDS

MAX_TITLE_LEN = 100

_TITLE_TEMPLATES_CURIOSITY = [
    "The {kw} Secret Nobody Tells You",
    "Nobody Talks About This {kw} Truth",
    "This {kw} Fact Will Surprise You",
    "The Hidden Truth About {kw}",
    "Why Everyone Is Wrong About {kw}",
]

_TITLE_TEMPLATES_HOWTO = [
    "How to Master {kw} in 60 Seconds",
    "{n} {kw} Mistakes You Must Avoid",
    "How {kw} Actually Works (Explained Fast)",
    "{n} {kw} Tips That Actually Work",
    "Stop Doing {kw} Wrong — Do This Instead",
]

_TITLE_TEMPLATES_KEYWORD = [
    "{Kw} Explained in 60 Seconds",
    "{Kw}: What You Need to Know",
    "{Kw} — The Full Story in One Minute",
    "Everything About {Kw}, Fast",
]

# --- GTA 6 mode ------------------------------------------------------------
# Every title mentions GTA 6; the keyword slot carries the clip's own
# topic (Lucia, Jason, Vice City, a leak, a heist, ...).

_TITLE_TEMPLATES_GTA6 = [
    "GTA 6 {Kw} — You Have to See This",
    "This GTA 6 {Kw} Moment Is Insane",
    "{Kw} in GTA 6: First Look in 60 Seconds",
    "GTA 6 {Kw} — The Detail Everyone Missed",
    "Why GTA 6 {Kw} Changes Everything",
    "GTA 6 {Kw} Just Broke the Internet",
]

GTA6_HASHTAGS = [
    "#gta6", "#gtavi", "#grandtheftauto6", "#vicecity",
    "#gta6shorts", "#rockstargames", "#gta6gameplay", "#shorts",
]

GTA6_TAGS = [
    "gta 6", "gta vi", "grand theft auto 6", "vice city",
    "rockstar games", "gta 6 gameplay", "gta 6 shorts",
    "gta 6 trailer", "gta 6 leak",
]

# Words that carry no information inside a "GTA 6 {Kw}" title.
_GTA6_TITLE_STOPWORDS = {"gta", "vi", "6", "grand", "theft", "auto"}


def extract_keywords(text, title="", top_n=12):
    """Top content words by frequency, title words boosted."""
    words = re.findall(r"[a-zA-Z\u0900-\u097f]{3,}", (text or "").lower())
    title_words = set(re.findall(r"[a-zA-Z\u0900-\u097f]{3,}", (title or "").lower()))
    freq = {}
    for w in words:
        if w in STOPWORDS:
            continue
        freq[w] = freq.get(w, 0) + 1
    for w in title_words:
        if w in freq:
            freq[w] += 3
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in ranked[:top_n]]


def _first_sentence(text, max_len=80):
    text = (text or "").strip()
    if not text:
        return ""
    m = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
    s = m[0].strip()
    if len(s) > max_len:
        s = s[: max_len - 3].rsplit(" ", 1)[0] + "..."
    return s


def _trim(title):
    if len(title) <= MAX_TITLE_LEN:
        return title
    return title[: MAX_TITLE_LEN - 3].rsplit(" ", 1)[0] + "..."


def _rule_based_titles(keywords, clip_text):
    kw = keywords[0] if keywords else "this"
    kw2 = keywords[1] if len(keywords) > 1 else kw
    n = 3 + (len(clip_text) % 3)  # deterministic 3-5
    titles = [
        _trim(_TITLE_TEMPLATES_CURIOSITY[len(kw) % len(_TITLE_TEMPLATES_CURIOSITY)].format(kw=kw)),
        _trim(_TITLE_TEMPLATES_HOWTO[len(kw2) % len(_TITLE_TEMPLATES_HOWTO)].format(kw=kw2, n=n)),
        _trim(_TITLE_TEMPLATES_KEYWORD[len(kw) % len(_TITLE_TEMPLATES_KEYWORD)].format(kw=kw, Kw=kw.capitalize())),
    ]
    # Ensure all three are distinct.
    seen = set()
    out = []
    for t in titles:
        if t not in seen:
            seen.add(t)
            out.append(t)
    while len(out) < 3:
        out.append(_trim(f"{kw.capitalize()} in 60 Seconds — Part {len(out) + 1}"))
    return out[:3]


def _gta6_rule_based_titles(keywords, clip_text):
    kws = [k for k in keywords if k.lower() not in _GTA6_TITLE_STOPWORDS]
    kw = (kws[0] if kws else (keywords[0] if keywords else "moment"))
    kw2 = (kws[1] if len(kws) > 1 else kw)
    picks = [
        _TITLE_TEMPLATES_GTA6[len(kw) % len(_TITLE_TEMPLATES_GTA6)],
        _TITLE_TEMPLATES_GTA6[(len(kw2) + 2) % len(_TITLE_TEMPLATES_GTA6)],
        _TITLE_TEMPLATES_GTA6[(len(clip_text) + 1) % len(_TITLE_TEMPLATES_GTA6)],
    ]
    titles = []
    for i, template in enumerate(picks):
        word = kw if i != 1 else kw2
        t = _trim(template.format(kw=word, Kw=word.capitalize()))
        if t not in titles:
            titles.append(t)
    while len(titles) < 3:
        titles.append(_trim(f"GTA 6 {kw.capitalize()} in 60 Seconds"))
    return titles[:3]


def _gta6_hashtags(keywords):
    tags = list(GTA6_HASHTAGS)
    for kw in keywords:
        tag = "#" + re.sub(r"[^a-z0-9]", "", kw.lower())
        if tag != "#" and tag not in tags:
            tags.append(tag)
    return tags[:12]


def _gta6_tags(keywords):
    tags = list(GTA6_TAGS)
    for kw in keywords:
        if kw not in tags:
            tags.append(kw)
    return tags[:12]


def _hashtags(keywords, extra=()):
    tags = ["shorts", "viral"]
    for kw in keywords:
        tag = re.sub(r"[^a-z0-9]", "", kw.lower())
        if tag and tag not in tags:
            tags.append(tag)
    for e in extra:
        tag = re.sub(r"[^a-z0-9]", "", str(e).lower())
        if tag and tag not in tags:
            tags.append(tag)
    tags = tags[:12]
    while len(tags) < 8:
        tags.append(f"shorts{len(tags)}")
    return ["#" + t for t in tags[:12]]


def _tags(keywords, title=""):
    tags = []
    for kw in keywords:
        if kw not in tags:
            tags.append(kw)
    for extra in ("shorts", "viral shorts", "youtube shorts"):
        if extra not in tags:
            tags.append(extra)
    if title:
        title_words = [w for w in title.split() if len(w) > 3]
        for w in title_words[:3]:
            if w.lower() not in tags:
                tags.append(w.lower())
    return tags[:12]


def _llm_titles(clip_text, keywords, title="", mode="generic"):
    """Optional LLM upgrade. Returns list of 3 titles or None on any failure."""
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not gemini_key and not openai_key:
        return None
    if mode == "gta6":
        prompt = (
            "Write exactly 3 YouTube Shorts titles (each under 100 characters) "
            "for this GTA 6 clip. Every title must mention GTA 6. One "
            "curiosity-driven, one reaction/hype, one keyword-led. Return ONLY "
            "a JSON array of 3 strings, no other text.\n\n"
            f"Video title: {title}\nKeywords: {', '.join(keywords[:6])}\n"
            f"Clip transcript: {clip_text[:600]}"
        )
    else:
        prompt = (
            "Write exactly 3 YouTube Shorts titles (each under 100 characters) "
            "for this clip. One curiosity-driven, one how-to/number, one keyword-led. "
            "Return ONLY a JSON array of 3 strings, no other text.\n\n"
            f"Video title: {title}\nKeywords: {', '.join(keywords[:6])}\n"
            f"Clip transcript: {clip_text[:600]}"
        )
    try:
        if gemini_key:
            url = ("https://generativelanguage.googleapis.com/v1beta/models/"
                   f"gemini-2.0-flash:generateContent?key={gemini_key}")
            body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.load(resp)
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
        else:
            url = "https://api.openai.com/v1/chat/completions"
            body = json.dumps({
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 300,
            }).encode()
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {openai_key}",
            })
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.load(resp)
            raw = data["choices"][0]["message"]["content"]
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").strip()
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        titles = json.loads(raw)
        titles = [_trim(str(t)) for t in titles if str(t).strip()][:3]
        if mode == "gta6":
            titles = [t if "gta 6" in t.lower() or "gta vi" in t.lower()
                      else _trim(f"GTA 6 — {t}") for t in titles]
        return titles if len(titles) == 3 else None
    except Exception:
        return None


def generate_seo(clip_text, video_title="", keywords=None, mode="generic"):
    """Generate the full SEO pack for one clip.

    mode="gta6" uses GTA 6 title templates, hashtags and tags;
    mode="generic" (default) keeps the original behaviour.

    Returns {titles: [3], description: str, hashtags: [8-12], tags: [8-12]}.
    """
    keywords = keywords or extract_keywords(clip_text, video_title)
    titles = _llm_titles(clip_text, keywords, video_title, mode=mode)
    if not titles:
        if mode == "gta6":
            titles = _gta6_rule_based_titles(keywords, clip_text)
        else:
            titles = _rule_based_titles(keywords, clip_text)

    hook = _first_sentence(clip_text, max_len=110)
    if mode == "gta6":
        description = (
            f"{hook}\n"
            f"Full video: {video_title or 'see the original video'}.\n"
            "More GTA 6 Shorts every day — like & subscribe!"
        )
        return {
            "titles": titles,
            "description": description,
            "hashtags": _gta6_hashtags(keywords),
            "tags": _gta6_tags(keywords),
        }
    description = (
        f"{hook}\n"
        f"Full video: {video_title or 'see the original video'}.\n"
        "Like & subscribe for more Shorts like this!"
    )
    return {
        "titles": titles,
        "description": description,
        "hashtags": _hashtags(keywords),
        "tags": _tags(keywords, video_title),
    }
