"""Cut vertical 1080x1920 clips with ffmpeg.

Two modes:
- "crop": scale-to-fill then center-crop (best for talking-head / full-frame).
- "blur": blurred background fill with the full frame fitted on top
  (best when the original framing must not lose anything).

Captions (an ASS file) can be burned in the same encode pass.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def _escape_filter_path(path) -> str:
    """Escape a path for use inside an ffmpeg filter argument."""
    return (str(path).replace("\\", "\\\\")
            .replace(":", "\\:")
            .replace("'", "\\'"))


def _video_filter(mode: str, captions_ass=None) -> str:
    if mode == "blur":
        filt = (
            "[0:v]split[a][b];"
            "[a]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,gblur=sigma=50[bg];"
            "[b]scale=1080:-2[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]"
        )
    else:  # crop (default)
        filt = ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,format=yuv420p[v]")
    if captions_ass:
        filt += f";[v]subtitles='{_escape_filter_path(captions_ass)}'[vout]"
        return filt, "[vout]"
    return filt, "[v]"


def cut_clip(input_path, start, end, output_path, mode="crop",
             captions_ass=None, crf=18):
    """Cut [start, end) from input_path into a vertical 1080x1920 MP4.

    Best-quality defaults: CRF 18 + medium preset + 192k audio.
    Returns the output path. Raises subprocess.CalledProcessError on failure.
    """
    duration = max(1.0, float(end) - float(start))
    filt, vlabel = _video_filter(mode, captions_ass)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{float(start):.2f}",
        "-t", f"{duration:.2f}",
        "-i", str(input_path),
        "-filter_complex", filt,
        "-map", vlabel,
        "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return Path(output_path)


def probe_duration(path) -> float:
    """Media duration in seconds via ffprobe."""
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return float(out.stdout.strip())


def probe_resolution(path):
    """(width, height) of the first video stream via ffprobe."""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=width,height",
           "-of", "csv=p=0", str(path)]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True)
    w, h = out.stdout.strip().split(",")
    return int(w), int(h)
