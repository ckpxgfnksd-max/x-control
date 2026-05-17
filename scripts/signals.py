"""Positive impression-lift signals — heuristics that mirror the ranker head
structure in `xai-org/x-algorithm`.

Per `home-mixer/scorers/ranking_scorer.rs` (combine_predictions), the final
ranking score is a weighted sum over ~14 positive engagement heads and ~5
negative-feedback heads. The numeric weights live in stripped params modules,
so we surface *which heads a draft plausibly activates* rather than predicting
magnitudes.

Each signal returns (score: float in [0, 1], reason: str). No network, no
side effects. Designed to be cheap to call from `approve.py` at draft time.

Heuristics are deliberately conservative — high signal means "the draft has
an obvious feature that maps to this head", not "this will get high reach".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# ── shared regex --------------------------------------------------------------
_OPEN_QUESTION = re.compile(r"\?\s*$")
_CONTRARIAN_FRAME = re.compile(
    r"\b("
    r"most\s+\w+\s+(are\s+wrong|miss|get\s+\w+\s+wrong)"
    r"|nobody\s+(talks|admits|says)"  # also matches an AI-slop opener — fine, we offset later
    r"|the\s+real\s+(reason|story|problem)"
    r"|unpopular\s+opinion"
    r"|actually\s+(\w+\s+){0,3}(wrong|backwards|opposite)"
    r")", re.I,
)
_ASSERTION = re.compile(
    r"\b(is|are|will|should|won't|can't|never|always)\b", re.I,
)
_HEDGE = re.compile(r"\b(i think|maybe|kind of|sort of|imho|i guess|probably|might)\b", re.I)
_NUMBERS = re.compile(r"\b\d[\d,]*(?:\.\d+)?\s*(?:%|x|×|bps|m|k|b|usd|\$)?\b", re.I)
_SERIES_MARKER = re.compile(
    r"\b("
    r"part\s+\d+(\s+of\s+\d+)?"
    r"|day\s+\d+(\s+of\s+\d+)?"
    r"|week\s+\d+"
    r"|episode\s+\d+"
    r"|chapter\s+\d+"
    r"|(\d+)/(\d+)"
    r"|weekly\s+(thread|update|brief)"
    r"|daily\s+(thread|update|brief)"
    r")", re.I,
)
_IDENTITY_TEASE_PATTERNS = (
    re.compile(r"\b(ex|former|previously)[- ]\w+", re.I),
    re.compile(r"\b(i\s+(built|ran|led|sold|founded|launched|shipped|wrote|spent))\b", re.I),
    re.compile(r"\b\d+\s+years?\s+(at|in|of|building|working)\b", re.I),
)
_GENERIC_OPENERS = re.compile(
    r"^\s*(thoughts|here's a thought|interesting|just\s+\w+|quick take|hmm|wow)",
    re.I,
)


@dataclass
class Signal:
    name: str
    score: float  # 0..1
    reason: str
    head: str  # which ranker head this maps to


# ── individual signals --------------------------------------------------------
def repostability(text: str) -> Signal:
    """Maps to `retweet` + `share_via_*` heads (ranking_scorer.rs).
    People retweet quotable, declarative claims — not hedged thinking-aloud.
    """
    body = text.strip()
    length = len(body)
    score = 0.0
    reasons: list[str] = []

    if 80 <= length <= 240:
        score += 0.4
        reasons.append("quotable length")
    elif length < 60:
        reasons.append("too short to quote")
    elif length > 240:
        reasons.append("too long to quote")

    if _ASSERTION.search(body):
        score += 0.3
        reasons.append("declarative")
    else:
        reasons.append("no assertion")

    if _HEDGE.search(body):
        score -= 0.2
        reasons.append("hedged")
    if _CONTRARIAN_FRAME.search(body):
        score += 0.3
        reasons.append("contrarian framing")

    score = max(0.0, min(1.0, score))
    reason = ", ".join(reasons) if reasons else "neutral"
    return Signal("repostability", score, reason, head="retweet/share")


def reply_worthiness(text: str) -> Signal:
    """Maps to `reply` head. Open questions and contrarian framings generate
    replies — but the same features overlap with negative-feedback risk, so
    callers should cross-reference with `negative_feedback_risk`.
    """
    body = text.strip()
    score = 0.0
    reasons: list[str] = []

    # Use the last non-empty line as "ending"
    last_line = next((ln.strip() for ln in reversed(body.splitlines()) if ln.strip()), "")
    if _OPEN_QUESTION.search(last_line):
        score += 0.5
        reasons.append("open question at end")
    if _CONTRARIAN_FRAME.search(body):
        score += 0.3
        reasons.append("contrarian frame invites pushback")
    if re.search(r"\b(what do you think|am i wrong|change my mind|prove me wrong)\b", body, re.I):
        # These are also engagement-bait risk markers — we score reply lift, but
        # the caller's risk panel will simultaneously flag this.
        score += 0.2
        reasons.append("explicit ask (also engagement-bait risk)")
    if not reasons:
        reasons.append("no reply hook")
    score = max(0.0, min(1.0, score))
    return Signal("reply-worthiness", score, ", ".join(reasons), head="reply")


def dwell_potential(text: str, tweet_count: int) -> Signal:
    """Maps to `dwell` + `dwell_time` + `click_dwell_time` continuous heads.
    Threads, line-broken structure, and embedded numbers/data force scroll
    pauses; one-liners zero out the dwell signal.
    """
    body = text.strip()
    score = 0.0
    reasons: list[str] = []

    if tweet_count >= 6:
        score += 0.6
        reasons.append(f"thread ({tweet_count} tweets) — strong dwell")
    elif tweet_count >= 3:
        score += 0.4
        reasons.append(f"short thread ({tweet_count}) — moderate dwell")
    elif "\n" in body and len(body) >= 180:
        score += 0.3
        reasons.append("multi-line standalone")
    else:
        reasons.append("single short tweet")

    nums = _NUMBERS.findall(body)
    if len(nums) >= 2:
        score += 0.2
        reasons.append(f"{len(nums)} numbers anchor attention")

    score = max(0.0, min(1.0, score))
    return Signal("dwell-potential", score, ", ".join(reasons), head="dwell/dwell_time")


def profile_click_pull(text: str, identity_hints: Iterable[str]) -> Signal:
    """Maps to `profile_click` head. Identity teases ("ex-<bigco>...", "I
    spent 5 years building X") pull viewers to your profile — but only if
    the draft frontmatter actually declares identity_hints. No declared
    identity → assume the draft does not lean on this lever.
    """
    body = text.strip()
    hints = [h.strip() for h in (identity_hints or []) if h and str(h).strip()]
    score = 0.0
    reasons: list[str] = []

    if not hints:
        return Signal(
            "profile-click-pull",
            0.0,
            "no identity_hints declared in frontmatter",
            head="profile_click",
        )

    matched_hints = [h for h in hints if re.search(re.escape(h), body, re.I)]
    if matched_hints:
        score += 0.5
        reasons.append(f"identity in text: {matched_hints[0]!r}")
    else:
        # Hints declared but not used — still score the structural tease
        reasons.append("hints declared, not in body")

    if any(p.search(body) for p in _IDENTITY_TEASE_PATTERNS):
        score += 0.3
        reasons.append("ex-/I-built-/years-at pattern")

    if re.search(r"\bhere'?s what nobody\b|\bwhat (i|they)\s+\w+\b", body, re.I):
        score += 0.2
        reasons.append("withholding tease")

    score = max(0.0, min(1.0, score))
    return Signal("profile-click-pull", score, ", ".join(reasons), head="profile_click")


def follow_author_reason(text: str) -> Signal:
    """Maps to `follow_author` head. Series markers ("part 2 of 5") and
    explicit recurring-value signals predict follow conversion. Generic
    one-off takes get a low score.
    """
    body = text.strip()
    score = 0.0
    reasons: list[str] = []

    if _SERIES_MARKER.search(body):
        score += 0.5
        reasons.append("series marker present")

    if re.search(r"\b(follow for|more like this|i post|every (day|week)|weekly|daily)\b", body, re.I):
        score += 0.2
        reasons.append("recurring-value signal")

    if _GENERIC_OPENERS.match(body):
        score -= 0.1
        reasons.append("generic opener")

    if not reasons:
        reasons.append("no series/recurring marker")

    score = max(0.0, min(1.0, score))
    return Signal("follow-author-reason", score, ", ".join(reasons), head="follow_author")


def topic_fit(topic_tags: Iterable[str], own_topics: Iterable[str]) -> Signal:
    """Inverse of OON multiplier via `TopicOonWeightFactor`. Posts whose
    topic_tags overlap with the account's recent topic mix qualify for the
    topic-browse surface in addition to the follow-graph surface.

    own_topics: set of topic strings derived from the last 30 days of
    tracker events (caller's responsibility — pulled from tracker.topic_mix()).
    """
    tags = {str(t).strip().lower() for t in (topic_tags or []) if t}
    own = {str(t).strip().lower() for t in (own_topics or []) if t}
    score = 0.0
    reasons: list[str] = []

    if not tags:
        return Signal(
            "topic-fit",
            0.0,
            "no topic_tags declared (TopicOonWeightFactor unused)",
            head="TopicOonWeightFactor",
        )
    if not own:
        return Signal(
            "topic-fit",
            0.5,
            f"tags {sorted(tags)} declared, no 30d baseline yet",
            head="TopicOonWeightFactor",
        )

    overlap = tags & own
    if overlap:
        score = min(1.0, 0.5 + 0.2 * len(overlap))
        reasons.append(f"overlap with 30d mix: {sorted(overlap)}")
    else:
        score = 0.2
        reasons.append(f"new territory (tags {sorted(tags)} not in 30d mix)")
    return Signal("topic-fit", score, ", ".join(reasons), head="TopicOonWeightFactor")


def negative_feedback_risk(risk_markers: Iterable[str]) -> Signal:
    """Inverse of `not_interested + block_author + mute_author + report +
    not_dwelled`. We don't reimplement risk detection — we read the markers
    that `queue.risk_markers()` already computed and weight the bad ones.

    Returns score *as risk* (higher = worse): caller renders LOW/MED/HIGH.
    """
    markers = list(risk_markers or [])
    if not markers:
        return Signal("neg-feedback-risk", 0.0, "no risk markers", head="neg-feedback")

    # Subset that maps directly to negative-feedback heads vs cosmetic.
    high_risk = {
        "engagement_bait",
        "callout_named_account",
        "ai_slop_openers",
        "shill_keywords",
        "guarantee_lang",
        "dm_solicitation",
    }
    medium_risk = {"em_dash_overuse", "emoji_spam", "numbered_list_in_one_tweet", "price_target"}

    high = [m for m in markers if m in high_risk]
    medium = [m for m in markers if m in medium_risk]
    other = [m for m in markers if m not in high_risk and m not in medium_risk]

    # Score is the worst class hit, lightly inflated by count.
    if high:
        score = min(1.0, 0.7 + 0.05 * len(high))
        label = f"HIGH ({len(high)}): " + ", ".join(high)
    elif medium:
        score = min(1.0, 0.4 + 0.05 * len(medium))
        label = f"MED ({len(medium)}): " + ", ".join(medium)
    else:
        score = 0.2
        label = "LOW: " + ", ".join(other) if other else "LOW"
    return Signal("neg-feedback-risk", score, label, head="neg-feedback")


# ── public API ---------------------------------------------------------------
def score_draft(
    text: str,
    *,
    tweet_count: int,
    frontmatter: dict | None = None,
    own_topics: Iterable[str] = (),
    risk_markers: Iterable[str] = (),
) -> list[Signal]:
    """Return the full signal panel for a draft. Caller renders.

    `text` is the full joined draft body (all tweets in a thread, blank-line
    separated). For dwell/topic/identity heuristics we operate on the joined
    text — distinguishing tweet-1 vs tweet-N is left to the caller.
    """
    fm = frontmatter or {}
    return [
        repostability(text),
        reply_worthiness(text),
        dwell_potential(text, tweet_count),
        profile_click_pull(text, fm.get("identity_hints") or ()),
        follow_author_reason(text),
        topic_fit(fm.get("topic_tags") or (), own_topics),
        negative_feedback_risk(risk_markers),
    ]


def bars(score: float, width: int = 5) -> str:
    """Render a 0-1 score as ●/○ bars for the CLI."""
    s = max(0.0, min(1.0, score))
    filled = int(round(s * width))
    return "●" * filled + "○" * (width - filled)


def neg_label(score: float) -> str:
    """Label for the inverted negative-feedback score (higher = worse)."""
    if score >= 0.7:
        return "HIGH"
    if score >= 0.4:
        return "MED"
    return "LOW"
