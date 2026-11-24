"""Vertical 1080x1920 thumbnails for clips.

Frame grab from the source video (same center-crop as the clip, but
without burned captions) + a gold "GTA 6" badge top-left + the clip's
SEO title in bold white on a dark bottom band. Pure ffmpeg, no extra
dependencies.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
GOLD = "0xE0A526"
DARK_BROWN = "0x2B1D0E"

TITLE_FONT_SIZE = 64
LINE_HEIGHT = 86
BAND_PAD = 56
MAX_LINE_CHARS = 20
MAX_LINES = 3


def wrap_title(title: str, max_chars=MAX_LINE_CHARS,
               max_lines=MAX_LINES) -> list:
    """Greedy word-wrap into at most max_lines lines of <= max_chars.

    Overlong single words are hard-split; overflow past max_lines is
    dropped with an ellipsis on the last line.
    """
    words = (title or "").split()
    lines = []
    current = ""
    for word in words:
        while len(word) > max_chars:
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:max_chars])
            word = word[max_chars:]
        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) <= max_chars:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if not lines:
        return ["GTA 6"]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        if len(last) > max_chars - 3:
            last = last[: max_chars - 3]
        lines[-1] = last.rstrip() + "..."
    return lines


def _escape_drawtext(text: str) -> str:
    """Escape a string for drawtext's text='...' option."""
    return (text.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace(":", "\\:")
            .replace("'", "\\'"))


def make_thumbnail(source_path, at_seconds, output_path, title,
                   badge="GTA 6"):
    """Grab a vertical frame at at_seconds and brand it.

    Returns the output path. Raises subprocess.CalledProcessError on
    failure.
    """
    lines = wrap_title(title)
    band_h = BAND_PAD * 2 + len(lines) * LINE_HEIGHT
    band_y = 1920 - band_h

    filters = [
        "scale=1080:1920:force_original_aspect_ratio=increase",
        "crop=1080:1920",
        # Dark bottom band for the title.
        f"drawbox=y={band_y}:w=1080:h={band_h}:color=black@0.72:t=fill",
        # Gold badge, top-left.
        f"drawbox=x=48:y=48:w=250:h=104:color={GOLD}:t=fill",
        f"drawtext=fontfile={FONT}:text='{_escape_drawtext(badge)}'"
        f":fontsize=58:fontcolor={DARK_BROWN}"
        f":x=48+(250-text_w)/2:y=48+(104-text_h)/2",
    ]
    for i, line in enumerate(lines):
        y = band_y + BAND_PAD + i * LINE_HEIGHT
        filters.append(
            f"drawtext=fontfile={FONT}:text='{_escape_drawtext(line)}'"
            f":fontsize={TITLE_FONT_SIZE}:fontcolor=white"
            f":x=(w-text_w)/2:y={y}"
        )

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{float(at_seconds):.2f}",
        "-i", str(source_path),
        "-frames:v", "1",
        "-vf", ",".join(filters),
        "-q:v", "2",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return Path(output_path)
