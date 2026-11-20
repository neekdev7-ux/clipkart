"""GTA 6 scorer: hype segments must outrank filler, chat spikes add a
bonus, and the reason must name the GTA 6 moment."""
from backend.gta6 import scorer as gta6
from backend.pipeline import score as base_score
from tests.conftest import words_from_text
from tests.test_score import FILLER_TEXT

HYPE_TEXT = (
    "Bhai dekh, Vice City ka naya trailer leak ho gaya, pagal scene hai! "
    "Lucia and Jason just pulled off the biggest heist in Leonida. "
    "Did you see that police chase through Ocean Drive? Insane! "
    "Rockstar finally revealed the full map and this new feature is OP. "
    "First look at the gameplay — this is the most crazy reveal ever. "
    "The wanted level chase is unreal, mast trailer, total banger. "
)

PLAIN_TEXT = (
    "So today we are going to talk about some stuff and things. "
    "There are a lot of different topics we could cover here. "
    "Let us begin with a general overview of the situation. "
)


def _mixed_transcript():
    # ~45s of hype, then ~100s of filler.
    return words_from_text((HYPE_TEXT * 2) + (FILLER_TEXT * 3))


def test_hype_bonus_positive_for_gta6_text():
    assert gta6.hype_bonus(HYPE_TEXT) > 0
    assert gta6.hype_bonus(HYPE_TEXT) <= 20
    assert gta6.hype_bonus(PLAIN_TEXT) == 0


def test_hype_hits_find_phrases_and_hinglish():
    hits = gta6.hype_hits(HYPE_TEXT)
    assert "vice city" in hits
    assert "police chase" in hits
    assert "bhai" in hits
    assert "pagal" in hits
    assert "leonida" in hits


def test_hype_window_scores_above_filler():
    words = _mixed_transcript()
    windows = base_score.build_windows(words, clip_seconds=45)
    assert windows
    hype_win = windows[0]  # starts at 0s: pure hype content
    hype_score, reason = gta6.score_window_gta6(
        hype_win, words, title="GTA 6 Trailer Reaction")
    late_win = [w for w in windows if w["start"] >= 60][0]
    late_score, _ = gta6.score_window_gta6(
        late_win, words, title="GTA 6 Trailer Reaction")
    assert hype_score > late_score
    assert hype_score >= 60
    assert "GTA 6" in reason


def test_chat_spike_bonus_raises_score_and_reason():
    words = _mixed_transcript()
    window = base_score.build_windows(words, clip_seconds=45)[0]
    plain, _ = gta6.score_window_gta6(window, words, title="GTA 6 Live")
    spiked, reason = gta6.score_window_gta6(
        window, words, title="GTA 6 Live", chat_bonus=15)
    assert spiked > plain
    assert spiked <= 100
    assert "chat spike" in reason


def test_chat_bonus_clamped_to_15():
    words = _mixed_transcript()
    window = base_score.build_windows(words, clip_seconds=45)[0]
    _, reason = gta6.score_window_gta6(window, words, chat_bonus=999)
    # No crash, still a valid 0-100 score.
    s, _ = gta6.score_window_gta6(window, words, chat_bonus=999)
    assert 0 <= s <= 100


def test_rank_clips_gta6_picks_hype_first():
    words = _mixed_transcript()
    clips = gta6.rank_clips_gta6(words, title="GTA 6 Live",
                                 clip_seconds=45, max_clips=3)
    assert 1 <= len(clips) <= 3
    assert clips[0]["start"] < 20, "top clip should be the hype segment"
    assert clips[0]["score"] >= clips[-1]["score"]
    for c in clips:
        assert 30 <= c["duration"] <= 60
        assert c["reason"]


def test_rank_clips_gta6_min_score_filters_filler():
    words = words_from_text(FILLER_TEXT * 4)
    clips = gta6.rank_clips_gta6(words, title="GTA 6 Live",
                                 clip_seconds=45, max_clips=3,
                                 min_score=90)
    assert clips == []


def test_rank_clips_gta6_chat_fn_applied():
    words = _mixed_transcript()
    # Chat spike only in the late filler region.
    clips = gta6.rank_clips_gta6(
        words, title="GTA 6 Live", clip_seconds=45, max_clips=3,
        chat_fn=lambda a, b: 15.0 if a >= 60 else 0.0)
    assert clips
    assert any("chat spike" in c["reason"] for c in clips)


def test_empty_transcript_returns_no_clips():
    assert gta6.rank_clips_gta6([], title="GTA 6") == []
