"""GTA 6 SEO: every title mentions GTA 6, hashtags/tags carry the
GTA 6 set, and the description credits the source stream."""
import pytest

from backend.gta6 import seo as gta6_seo

CLIP_TEXT = (
    "Bhai dekh, Vice City ka naya trailer leak ho gaya, pagal scene hai! "
    "Lucia and Jason just pulled off the biggest heist in Leonida. "
    "Did you see that police chase through Ocean Drive? Insane!"
)


@pytest.fixture(autouse=True)
def _no_llm_keys(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_titles_mention_gta6_and_fit():
    pack = gta6_seo.generate_gta6_seo(CLIP_TEXT, stream_title="GTA 6 Live")
    assert len(pack["titles"]) == 3
    assert len(set(pack["titles"])) == 3, "titles must be distinct"
    for t in pack["titles"]:
        assert len(t) <= 100
        assert "gta 6" in t.lower() or "gta vi" in t.lower()


def test_hashtags_include_gta6_set():
    pack = gta6_seo.generate_gta6_seo(CLIP_TEXT)
    tags = pack["hashtags"]
    assert 8 <= len(tags) <= 12
    assert all(h.startswith("#") for h in tags)
    for required in ("#GTA6", "#GTAVI", "#GTA6Shorts", "#ViceCity",
                     "#RockstarGames"):
        assert required in tags


def test_tags_include_gta6_set():
    pack = gta6_seo.generate_gta6_seo(CLIP_TEXT)
    tags = [t.lower() for t in pack["tags"]]
    assert 8 <= len(tags) <= 12
    for required in ("gta 6", "gta vi", "grand theft auto 6", "vice city",
                     "rockstar games"):
        assert required in tags


def test_description_credits_source_stream():
    pack = gta6_seo.generate_gta6_seo(
        CLIP_TEXT, stream_title="GTA 6 Trailer Reaction LIVE",
        stream_url="https://www.youtube.com/watch?v=abc123",
        channel="StreamerBhai")
    desc = pack["description"]
    assert "GTA 6 Trailer Reaction LIVE" in desc
    assert "StreamerBhai" in desc
    assert "https://www.youtube.com/watch?v=abc123" in desc
    assert "subscribe" in desc.lower()


def test_seo_works_without_stream_info():
    pack = gta6_seo.generate_gta6_seo(CLIP_TEXT)
    assert len(pack["titles"]) == 3
    assert len(pack["hashtags"]) >= 8
    assert pack["description"].strip()
