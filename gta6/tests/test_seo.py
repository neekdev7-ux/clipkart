"""SEO: 3 titles (<=100 chars), 8-12 hashtags, 8-12 tags, description."""
from backend.pipeline import seo

CLIP_TEXT = (
    "Did you know this secret mistake costs you money every single day? "
    "Here is the truth nobody tells you about saving money. "
    "Most people never check their bank statements and that is shocking."
)


def test_generate_seo_shape():
    pack = seo.generate_seo(CLIP_TEXT, video_title="Money Saving Tips")
    assert len(pack["titles"]) == 3
    assert all(isinstance(t, str) and t for t in pack["titles"])
    assert all(len(t) <= 100 for t in pack["titles"])
    assert len(set(pack["titles"])) == 3, "titles must be distinct"
    assert 8 <= len(pack["hashtags"]) <= 12
    assert all(h.startswith("#") for h in pack["hashtags"])
    assert 8 <= len(pack["tags"]) <= 12
    assert pack["description"].strip()
    assert "subscribe" in pack["description"].lower()


def test_keywords_come_from_clip():
    kws = seo.extract_keywords(CLIP_TEXT, "Money Saving Tips")
    assert "money" in kws
    assert all(len(k) >= 3 for k in kws)


def test_seo_works_without_title():
    pack = seo.generate_seo(CLIP_TEXT)
    assert len(pack["titles"]) == 3
    assert len(pack["hashtags"]) >= 8
