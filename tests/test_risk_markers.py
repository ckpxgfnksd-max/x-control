"""Risk-marker regex coverage. One positive case per pattern + two negatives.

These regexes feed signals.negative_feedback_risk(), so a regression here
silently breaks the impression-lift panel as well as the original risk panel.
"""
from __future__ import annotations

import pytest

from scripts import queue
from scripts.queue import Draft


def _make(body: str) -> Draft:
    return Draft(path=__import__("pathlib").Path("/tmp/x.md"), frontmatter={}, body=body)


@pytest.mark.parametrize(
    "marker, body",
    [
        ("price_target", "ETH $5000 price target by EOY"),
        ("guarantee_lang", "This is guaranteed to 10x by Friday"),
        ("shill_keywords", "Quiet 100x moonshot, in early"),
        ("dm_solicitation", "DM me for the alpha"),
        ("callout_named_account", "@vitalik is wrong about rollups"),
        ("engagement_bait", "RT if you agree"),
        ("ai_slop_openers", "Let me explain why this matters"),
        ("em_dash_overuse", "First — second — third — fourth point all important"),
        ("emoji_spam", "Big news 🚀🚀🚀🚀🚀 incoming"),
        ("numbered_list_in_one_tweet", "Three things: 1. liquidity 2. velocity 3. accrual"),
        ("contains_url_$0.20_per_post", "Read more at https://example.com"),
    ],
)
def test_positive_cases(marker, body):
    d = _make(body)
    markers = d.risk_markers()
    assert marker in markers, f"expected {marker} in {markers!r} for body {body!r}"


@pytest.mark.parametrize(
    "body",
    [
        # Calm declarative claim, no triggers.
        "Tokenomics has a 3-act structure: emission, accrual, exit.",
        # Question without engagement-bait triggers.
        "Curious how others think about staking lock-up windows past 6 months.",
    ],
)
def test_negative_cases(body):
    d = _make(body)
    markers = d.risk_markers()
    # No URL → no cost flag either. Empty list is the success state.
    assert markers == [], f"expected no markers for {body!r}, got {markers}"


def test_thread_em_dashes_flagged_once_per_thread():
    """The em-dash check runs per-tweet but only adds the marker once."""
    body = (
        "First tweet — has — many — dashes — yes.\n\n"
        "Second tweet — also — has — many — dashes — too."
    )
    d = _make(body)
    markers = d.risk_markers()
    assert markers.count("em_dash_overuse") == 1
