"""Pytest setup: project root on sys.path, isolated data dir for API tests."""
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Isolate the API's SQLite DB + job files per test session.
_tmp = Path(tempfile.mkdtemp(prefix="clipnova-test-"))
os.environ.setdefault("CLIPNOVA_DATA", str(_tmp))


def words_from_text(text, word_seconds=0.5):
    """Fake word-level transcript: each word gets a fixed duration."""
    words = []
    t = 0.0
    for w in text.split():
        words.append({"word": w, "start": round(t, 2), "end": round(t + word_seconds, 2)})
        t += word_seconds
    return words
