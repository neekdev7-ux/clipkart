"""Transcription with faster-whisper (imported lazily).

Extracts 16kHz mono audio with ffmpeg, then runs Whisper with
word-level timestamps. Language is auto-detected (Hindi + English
both supported). The model (~150MB for base) downloads on first run
from Hugging Face and is cached afterwards.

Offline fix: when the requested model is already in the local
Hugging Face cache, HF_HUB_OFFLINE=1 is set before loading it, so
faster-whisper never hangs on a Hugging Face connectivity check
(the GTA 6 live monitor hit exactly this: every segment failed at
model load until the load was pointed at the local cache). First-run
downloads still work — the flag is only set when the model is cached.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _hf_cache_dir() -> Path:
    """Hugging Face hub cache root, honouring HF_HOME / HF_HUB_CACHE."""
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    if os.environ.get("HF_HOME"):
        return Path(os.environ["HF_HOME"]) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _model_is_cached(model_size: str) -> bool:
    """True when `model_size` needs no download to load.

    Covers a local path (dir or file) and a faster-whisper model
    already in the HF cache (repo Systran/faster-whisper-<size>,
    or a full "org/name" repo id).
    """
    if not model_size:
        return False
    if Path(model_size).exists():
        return True
    repo = model_size if "/" in model_size else f"Systran/faster-whisper-{model_size}"
    repo_dir = _hf_cache_dir() / ("models--" + repo.replace("/", "--"))
    return any(repo_dir.glob("snapshots/*/model.bin"))


def _use_local_model_if_cached(model_size: str) -> None:
    """Set HF_HUB_OFFLINE=1 when the model is already cached locally.

    faster-whisper checks Hugging Face at load time even for cached
    models; on a flaky/blocked connection that check hangs or errors
    and transcription never starts. The env flag makes the load use
    the local cache only. Deliberately not set when the model is
    missing, so the first run can still download it.
    """
    if _model_is_cached(model_size):
        os.environ["HF_HUB_OFFLINE"] = "1"


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

    _use_local_model_if_cached(model_size)
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
