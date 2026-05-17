"""Positive-signal heuristic coverage.

Each ranker head gets at least one assertion that the score moves in the
expected direction for a representative input. We assert ranges, not exact
values — the heuristics will tune over time."""
from __future__ import annotations

import pytest

from scripts import signals


def test_repostability_quotable_declarative():
    s = signals.repostability(
        "Tokenomics is a 3-act structure: emission, accrual, exit. Skip act 2 and the model breaks."
    )
    assert s.score >= 0.6, f"expected high repostability, got {s.score}: {s.reason}"
    assert "declarative" in s.reason


def test_repostability_hedged_short():
    s = signals.repostability("I think maybe staking is good.")
    assert s.score <= 0.4, f"hedged + short should score low, got {s.score}: {s.reason}"
    assert "hedged" in s.reason


def test_reply_worthiness_open_question():
    s = signals.reply_worthiness("Most token launches fail. Why does nobody discuss the cliff math?")
    assert s.score >= 0.5
    assert "question" in s.reason


def test_reply_worthiness_no_hook():
    s = signals.reply_worthiness("Quick screenshot from today's reading.")
    assert s.score == 0.0


def test_dwell_potential_thread():
    s = signals.dwell_potential("body doesn't matter for tweet_count path", tweet_count=8)
    assert s.score >= 0.5
    assert "thread" in s.reason.lower()


def test_dwell_potential_single_short():
    s = signals.dwell_potential("one line, no breaks", tweet_count=1)
    assert s.score < 0.4


def test_profile_click_no_hints():
    s = signals.profile_click_pull("Some normal post", identity_hints=[])
    assert s.score == 0.0
    assert "no identity_hints" in s.reason


def test_profile_click_matched_hint():
    s = signals.profile_click_pull(
        "Ex-Binance listing team here — the part exchanges never explain about your token review.",
        identity_hints=["ex-Binance listing"],
    )
    assert s.score >= 0.5
    assert "identity" in s.reason.lower()


def test_follow_author_series_marker():
    s = signals.follow_author_reason("Part 3 of 5 on tokenomics — here we cover vesting cliffs.")
    assert s.score >= 0.4
    assert "series" in s.reason.lower()


def test_topic_fit_overlap():
    s = signals.topic_fit(
        topic_tags=["tokenomics", "defi"],
        own_topics=["tokenomics", "ai", "claude"],
    )
    assert s.score >= 0.5
    assert "overlap" in s.reason


def test_topic_fit_new_territory():
    s = signals.topic_fit(
        topic_tags=["weather"],
        own_topics=["tokenomics", "defi"],
    )
    assert s.score < 0.5
    assert "new territory" in s.reason


def test_negative_feedback_risk_high():
    s = signals.negative_feedback_risk(["engagement_bait", "ai_slop_openers"])
    assert s.score >= 0.7
    assert signals.neg_label(s.score) == "HIGH"


def test_negative_feedback_risk_low():
    s = signals.negative_feedback_risk([])
    assert s.score == 0.0
    assert signals.neg_label(s.score) == "LOW"


def test_score_draft_returns_seven_signals():
    """The full panel hits every head exactly once."""
    panel = signals.score_draft(
        "Tokenomics has a 3-act structure. Part 1 of 3.",
        tweet_count=1,
        frontmatter={"topic_tags": ["tokenomics"], "identity_hints": ["ex-Binance"]},
        own_topics=["tokenomics", "defi"],
        risk_markers=[],
    )
    names = [s.name for s in panel]
    expected = {
        "repostability",
        "reply-worthiness",
        "dwell-potential",
        "profile-click-pull",
        "follow-author-reason",
        "topic-fit",
        "neg-feedback-risk",
    }
    assert set(names) == expected, f"missing or extra signals: {set(names) ^ expected}"
    for s in panel:
        assert 0.0 <= s.score <= 1.0


def test_bars_rendering():
    assert signals.bars(0.0) == "○○○○○"
    assert signals.bars(1.0) == "●●●●●"
    assert len(signals.bars(0.5)) == 5
