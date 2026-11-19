"""Word-level ASS subtitles with karaoke-style highlight.

Groups words into short lines (max ~4 words / ~1.8s), emits one Dialogue
line per group with \\k karaoke tags so the current word highlights in
gold while the rest stays white. Burned into the clip with ffmpeg's
subtitles filter (see cut.py, which chains it into the same encode).
"""
from __future__ import annotations

from pathlib import Path

ASS_HEADER = """[Script Info]
Title: ClipNova Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,64,&H00FFFFFF,&H0000C8F0,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,60,60,480,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def format_ass_time(seconds: float) -> str:
    """ASS timestamp H:MM:SS.cc (centiseconds)."""
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def group_words(words, max_words=4, max_seconds=1.8):
    """Group consecutive words into caption lines."""
    groups = []
    current = []
    for w in words:
        if current:
            span = w["end"] - current[0]["start"]
            if len(current) >= max_words or span > max_seconds:
                groups.append(current)
                current = []
        current.append(w)
    if current:
        groups.append(current)
    return groups


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def build_ass(words, clip_start, clip_end, out_path):
    """Write an ASS file for words inside [clip_start, clip_end].

    Times are relative to the clip start. Returns the path written.
    """
    in_clip = [w for w in words if w["end"] > clip_start and w["start"] < clip_end]
    lines = [ASS_HEADER]
    for group in group_words(in_clip):
        start = max(0.0, group[0]["start"] - clip_start)
        end = min(clip_end - clip_start, group[-1]["end"] - clip_start)
        if end <= start:
            continue
        parts = []
        for w in group:
            dur_cs = max(1, int(round((w["end"] - w["start"]) * 100)))
            parts.append("{\\k%d}%s" % (dur_cs, _escape_ass_text(w["word"].strip())))
        text = " ".join(parts)
        lines.append(
            f"Dialogue: 0,{format_ass_time(start)},{format_ass_time(end)},"
            f"Default,,0,0,0,,{text}"
        )
    Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return Path(out_path)
