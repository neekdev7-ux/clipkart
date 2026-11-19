"""Transcription with faster-whisper (imported lazily).

Extracts 16kHz mono audio with ffmpeg, then runs Whisper with
word-level timestamps. Language is auto-detected (Hindi + English
both supported). The model (~150MB for base) downloads on first run
from Hugging Face and is cached afterwards.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def extract_audio(video_path, wav_path) -> Path:
    """Extract 16kHz mono WAV for Whisper + energy profiling."""
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(wav_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return Path(wav_path)


def transcribe(video_path, model_size=None, language=None, work_dir=None):
    """Transcribe a video. Returns {words, language, duration}.

    words: [{word, start, end}, ...] with word-level timestamps.
    """
    import faster_whisper  # lazy: heavy dep, not needed for tests

    model_size = model_size or os.environ.get("WHISPER_MODEL", "base")
    work_dir = Path(work_dir) if work_dir else Path(video_path).parent
    work_dir.mkdir(parents=True, exist_ok=True)
    wav_path = work_dir / "audio.wav"
    extract_audio(video_path, wav_path)

    model = faster_whisper.WhisperModel(
        model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(wav_path), language=language, word_timestamps=True,
        beam_size=1, vad_filter=True,
    )
    words = []
    for seg in segments:
        for w in (seg.words or []):
            words.append({
                "word": w.word.strip(),
                "start": round(w.start, 2),
                "end": round(w.end, 2),
            })
    return {
        "words": words,
        "language": info.language,
        "duration": info.duration,
        "wav_path": str(wav_path),
    }
