"""GTA 6 SEO pack for clips: titles, description, hashtags, tags.

Rule-based by default — no API key required. If GEMINI_API_KEY or
OPENAI_API_KEY is set, titles are optionally upgraded via that API,
with the rule-based output as a fallback on any failure.

Every pack carries a source-credit line for the original stream:
auto-reposting other creators' streams risks copyright strikes and
reused-content issues, so credit is always included.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

from ..pipeline.seo import MAX_TITLE_LEN, _first_sentence, _trim, extract_keywords

GTA6_HASHTAGS = [
    "#GTA6", "#GTAVI", "#GTA6Shorts", "#ViceCity",
    "#RockstarGames", "#GTA6Gameplay", "#Shorts",
]

GTA6_TAGS = [
    "gta 6", "gta vi", "grand theft auto 6", "vice city",
    "rockstar games", "gta 6 gameplay", "gta 6 shorts",
    "gta 6 trailer", "gta 6 leak",
]

_TITLE_TEMPLATES = [
    "GTA 6 {Kw} — You Have to See This",
    "This GTA 6 {Kw} Moment Is Insane",
    "{Kw} in GTA 6: First Look in 60 Seconds",
    "GTA 6 {Kw} — The Detail Everyone Missed",
    "Why GTA 6 {Kw} Changes Everything",
    "GTA 6 {Kw} Just Broke the Internet",
]


def _rule_based_titles(keywords, clip_text):
    kws = [k for k in keywords
           if k.lower() not in {"gta", "vi", "6", "grand", "theft", "auto"}]
    kw = (kws[0] if kws else (keywords[0] if keywords else "moment"))
    kw2 = (kws[1] if len(kws) > 1 else kw)
    picks = [
        _TITLE_TEMPLATES[len(kw) % len(_TITLE_TEMPLATES)],
        _TITLE_TEMPLATES[(len(kw2) + 2) % len(_TITLE_TEMPLATES)],
        _TITLE_TEMPLATES[(len(clip_text) + 1) % len(_TITLE_TEMPLATES)],
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


def _llm_titles(clip_text, keywords, stream_title=""):
    """Optional LLM upgrade. Returns 3 titles or None on any failure."""
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not gemini_key and not openai_key:
        return None
    prompt = (
        "Write exactly 3 YouTube Shorts titles (each under 100 characters) "
        "for this GTA 6 clip. Every title must mention GTA 6. One "
        "curiosity-driven, one reaction/hype, one keyword-led. Return ONLY "
        "a JSON array of 3 strings, no other text.\n\n"
        f"Stream title: {stream_title}\nKeywords: {', '.join(keywords[:6])}\n"
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
        titles = [_trim(str(t)) for t in json.loads(raw) if str(t).strip()][:3]
        titles = [t if "gta 6" in t.lower() or "gta vi" in t.lower()
                  else _trim(f"GTA 6 — {t}") for t in titles]
        return titles if len(titles) == 3 else None
    except Exception:
        return None


def _hashtags(keywords):
    tags = list(GTA6_HASHTAGS)
    for kw in keywords:
        tag = "#" + re.sub(r"[^a-z0-9]", "", kw.lower())
        if tag != "#" and tag not in tags:
            tags.append(tag)
    return tags[:12]


def _tags(keywords):
    tags = list(GTA6_TAGS)
    for kw in keywords:
        if kw not in tags:
            tags.append(kw)
    return tags[:12]


def generate_gta6_seo(clip_text, stream_title="", stream_url="",
                      channel="", keywords=None):
    """Full GTA 6 SEO pack for one clip.

    Returns {titles: [3], description: str, hashtags: [8-12],
    tags: [8-12]}. Description always credits the source stream.
    """
    keywords = keywords or extract_keywords(clip_text, stream_title)
    titles = _llm_titles(clip_text, keywords, stream_title)
    if not titles:
        titles = _rule_based_titles(keywords, clip_text)

    hook = _first_sentence(clip_text, max_len=110)
    credit = ""
    if stream_title:
        credit = f"\nSource: {stream_title}"
        if channel:
            credit += f" by {channel}"
        if stream_url:
            credit += f" — {stream_url}"
    description = (
        f"{hook}\n"
        "More GTA 6 Shorts every day — like & subscribe!"
        f"{credit}"
    )
    return {
        "titles": titles,
        "description": description,
        "hashtags": _hashtags(keywords),
        "tags": _tags(keywords),
    }
