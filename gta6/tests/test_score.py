"""Scoring: strong hooks must outrank filler; windows must be 30-60s;
overlapping winners must be deduplicated."""
from backend.pipeline import score
from tests.conftest import words_from_text

HOOK_TEXT = (
    "Did you know this secret mistake costs you money every single day? "
    "Here is the truth nobody tells you about saving money. "
    "Most people never check their bank statements and that is shocking. "
    "I lost two thousand rupees last month because of one hidden fee. "
    "How can you stop this from happening to you right now? "
    "The answer is amazing and it takes only five minutes to fix. "
    "Remember this story because it will save your money forever. "
)

FILLER_TEXT = (
    "So today we are going to talk about some stuff and things. "
    "There are a lot of different topics we could cover here. "
    "Let us begin with a general overview of the situation. "
    "As you can see there are many aspects to consider overall. "
    "We will go through each point one by one in this video. "
    "It is important to understand the basic background first. "
    "Moving on to the next part of our discussion today. "
    "There is nothing particularly special about this section. "
    "We are just filling time with ordinary plain sentences here. "
    "This part of the video is calm and uneventful overall. "
)


def _mixed_transcript():
    # ~50s of hook content, then ~100s of filler.
    return words_from_text((HOOK_TEXT * 2) + (FILLER_TEXT * 3))


def test_hook_window_scores_above_filler():
    words = _mixed_transcript()
    windows = score.build_windows(words, clip_seconds=45)
    assert windows, "expected candidate windows"
    hook_win = windows[0]  # starts at 0s: pure hook content
    hook_score, _ = score.score_window(hook_win, words, title="Money Saving Tips")
    # A late window is pure filler.
    late_win = [w for w in windows if w["start"] >= 60][0]
    late_score, _ = score.score_window(late_win, words, title="Money Saving Tips")
    assert hook_score > late_score
    assert hook_score >= 50


def test_rank_clips_picks_hook_first_and_dedupes():
    words = _mixed_transcript()
    clips = score.rank_clips(words, title="Money Saving Tips",
                             clip_seconds=45, max_clips=3)
    assert 1 <= len(clips) <= 3
    assert clips[0]["start"] < 20, "top clip should be the hook segment"
    assert clips[0]["score"] >= clips[-1]["score"]
    # No two picked clips may overlap by more than 30% of the shorter.
    for i in range(len(clips)):
        for j in range(i + 1, len(clips)):
            assert score._overlap_ratio(clips[i], clips[j]) <= 0.3
    for c in clips:
        assert 30 <= c["duration"] <= 60
        assert c["reason"]


def test_windows_are_sentence_aligned_and_bounded():
    words = _mixed_transcript()
    for w in score.build_windows(words, clip_seconds=45):
        assert 30 <= w["end"] - w["start"] <= 60
        assert w["text"].strip()


def test_empty_transcript_returns_no_clips():
    assert score.rank_clips([], title="x") == []
