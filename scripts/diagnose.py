#!/usr/bin/env python3
"""Algo-grounded diagnostic — re-runnable productization of the one-off
2026-05-16 diagnostic that produced the current cap + brief-gate rules.

Reads the most recent `_pulse_data_*.json` dump + tracker history.
Outputs a structured report grounded in `xai-org/x-algorithm` source signals.

Usage: python scripts/diagnose.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import tracker                                      # noqa: E402

PULSE_DIR = Path.home() / "Documents" / "Last30Days"
OUT = PULSE_DIR / f"algo-diagnosis-{date.today().isoformat()}.md"


# ── helpers ──────────────────────────────────────────────────────────────────
def _latest_pulse_data() -> Path | None:
    candidates = sorted(PULSE_DIR.glob("_pulse_data_*.json"))
    return candidates[-1] if candidates else None


def _is_reply(text: str) -> bool:
    return text.lstrip().startswith("@")


def _is_cn(text: str) -> bool:
    return bool(re.search(r"[一-鿿]", text))


def _has_link(text: str) -> bool:
    return bool(re.search(r"https?://|t\.co/", text))


def _own_stats(data: dict) -> dict:
    own = data.get("own_tweets") or []
    cn = sum(1 for t in own if _is_cn(t.get("text", "")))
    en = len(own) - cn
    replies = sum(1 for t in own if _is_reply(t.get("text", "")))
    originals = len(own) - replies
    with_link = sum(1 for t in own if _has_link(t.get("text", "")))
    likes_total = sum((t.get("like_count") or 0) for t in own)
    rts_total = sum((t.get("retweet_count") or 0) for t in own)
    reps_total = sum((t.get("reply_count") or 0) for t in own)
    imps_total = sum((t.get("impression_count") or 0) for t in own)
    trapped = sum(
        1 for t in own
        if (t.get("reply_count") or 0) >= 3 and (t.get("like_count") or 0) <= 1
    )
    return {
        "n": len(own),
        "cn": cn, "en": en,
        "replies": replies, "originals": originals,
        "with_link": with_link,
        "likes_total": likes_total,
        "rts_total": rts_total,
        "reps_total": reps_total,
        "imps_total": imps_total,
        "trapped": trapped,
        "reply_ratio": replies / max(len(own), 1),
        "avg_imps": imps_total / max(len(own), 1),
        "avg_likes": likes_total / max(len(own), 1),
        "like_per_imp_pct": (likes_total / max(imps_total, 1)) * 100,
        "tweets": own,
    }


def _coverage_table() -> str:
    """Static-but-current snapshot of which algo levers are wired."""
    rows = [
        ("`OON_WEIGHT_FACTOR`", "`oon_scorer.rs:21`",
         "✅ Wired", "OON-trapped detection + TL;DR; affects per-tweet flagging"),
        ("`AuthorDiversityDecay` / `Floor`", "`ranking_scorer.rs:195-196`",
         "✅ Wired", "Burst warning (≥4/24h digest, ≥2/4h CLI), 3-standalone hard cap in approve.py"),
        ("Negative feedback weights (4)", "`ranking_scorer.rs:42-64`",
         "✅ Wired", "9 risk markers in queue.py: callout_named_account, engagement_bait, ai_slop_openers, em_dash_overuse, emoji_spam, numbered_list_in_one_tweet, price_target, guarantee_lang, shill_keywords, dm_solicitation"),
        ("19 positive engagement actions", "`weighted_scorer.rs:49-67`",
         "⚠️ Partial", "Surfaced as counts only; no per-action optimization advice"),
        ("`VQV_WEIGHT` / `MIN_VIDEO_DURATION_MS`", "`weighted_scorer.rs:72-80`",
         "⚠️ Partial", "Brief-only; surfaced as 'video gap' in weekly review"),
        ("Author hash embeddings", "`phoenix/recsys_model.py:99`",
         "⚠️ Partial", "Specialty consistency advice in diagnostic; not enforced inline"),
        ("Post age window (80h)", "`phoenix/recsys_model.py:33`",
         "✅ Wired", "Sunday weekly review fetches 24-80h tail via owned-reads"),
        ("`TopicOonWeightFactor`", "`ranking_scorer.rs:221-222`",
         "❌ Gap", "Topic-browse OON discount unused; could feed in /last30days trending"),
        ("Premium boost (magnitude unknown)", "feature-switches, runtime",
         "⚠️ Partial", "Premium long-form lane surfaced in weekly review gaps"),
        ("Time-of-day penalty", "(none in source)",
         "✅ Correctly absent", "Folklore quashed in x-brief; no false rule asserted"),
    ]
    lines = [
        "| Algo signal | Source | Status | Implementation in x-control |",
        "|---|---|:---:|---|",
    ]
    for sig, src, status, impl in rows:
        lines.append(f"| {sig} | {src} | {status} | {impl} |")
    return "\n".join(lines)


# ── render ───────────────────────────────────────────────────────────────────
def render(data: dict, stats: dict, ship_summary: dict) -> str:
    today = data.get("today") or date.today().isoformat()
    own_handle = data.get("own_handle", "you")
    n = stats["n"]
    imps = stats["imps_total"]
    likes = stats["likes_total"]
    lr = stats["like_per_imp_pct"]
    avg_imps = stats["avg_imps"]
    avg_likes = stats["avg_likes"]
    reply_ratio = stats["reply_ratio"] * 100

    health = "RESONANCE PROBLEM" if (lr < 0.3 and n >= 3) else "WITHIN HEALTHY RANGE"
    health_emoji = "⚠️" if health == "RESONANCE PROBLEM" else "✓"

    lines: list[str] = []
    lines.append(f"# Algo diagnosis — @{own_handle}")
    lines.append(f"**Date:** {today}  ·  **Source:** xai-org/x-algorithm (Rust, May 2026)")
    lines.append("")

    # TL;DR
    lines.append("## TL;DR")
    lines.append("")
    lines.append(
        f"**{n} posts · {imps:,} impressions · {likes} likes · {lr:.2f}% like-per-imp rate.** "
        f"{health_emoji} **{health}.** "
    )
    if health == "RESONANCE PROBLEM":
        lines.append(
            "The algorithm is showing your content (impressions are fine) but viewers "
            "aren't engaging (likes are not coming back). Healthy accounts run 0.5-2% "
            "like-per-impression. Top 3 moves: cut replies (currently "
            f"{reply_ratio:.0f}% of posts), ship a thread this week, add 1 EN post per day."
        )
    else:
        lines.append("Engagement-density is in healthy range; focus on volume + consistency.")
    lines.append("")

    # Coverage audit
    lines.append("## Part 1 — Algo signal coverage in x-control")
    lines.append("")
    lines.append(_coverage_table())
    lines.append("")

    # Account state
    lines.append("## Part 2 — Your account state (last 24h)")
    lines.append("")
    lines.append("| Metric | Value | Read |")
    lines.append("|---|---:|---|")
    lines.append(f"| Posts | {n} | "
                 f"{'Burst territory (≥4)' if n >= 4 else 'OK'} |")
    lines.append(f"| Total impressions | {imps:,} | "
                 f"{'Reach is fine' if avg_imps > 100 else 'Low reach baseline'} |")
    lines.append(f"| Total likes | {likes} | "
                 f"{'Conversion broken' if likes / max(n,1) < 1 else 'OK'} |")
    lines.append(f"| Total RTs | {stats['rts_total']} | "
                 f"{'Zero amplification' if stats['rts_total'] == 0 else 'Some amplification'} |")
    lines.append(f"| Total replies received | {stats['reps_total']} | "
                 f"{'OK' if stats['reps_total'] >= 3 else 'Cold audience'} |")
    lines.append(f"| Like-per-impression rate | **{lr:.3f}%** | "
                 f"{'~10× below healthy baseline' if lr < 0.3 else 'In range'} |")
    lines.append(f"| Language mix | {stats['cn']} CN / {stats['en']} EN | "
                 f"{'Single-pool ceiling' if stats['en'] == 0 and stats['cn'] >= 3 else 'OK'} |")
    lines.append(f"| Reply ratio | {stats['replies']}/{n} ({reply_ratio:.0f}%) | "
                 f"{'Too high — replies do not fan to your followers' if reply_ratio > 30 else 'OK'} |")
    lines.append(f"| Posts with links | {stats['with_link']}/{n} | "
                 f"(folklore says link-penalty; source does not confirm) |")
    lines.append(f"| OON-trapped tweets | {stats['trapped']} | "
                 f"{'Suppression risk' if stats['trapped'] > 0 else 'Good — no argument-trees'} |")
    lines.append(f"| Unanswered mentions | {len((data.get('own_mentions') or {}).get('data') or [])} | "
                 "Reply queue going stale |")
    lines.append("")

    # Per-tweet
    if n:
        lines.append("### Per-tweet breakdown (ranked by impressions)")
        lines.append("")
        lines.append("```")
        lines.append("imp  like rep  fmt    note")
        ranked = sorted(stats["tweets"], key=lambda t: -(t.get("impression_count") or 0))
        for t in ranked:
            l = t.get("like_count") or 0
            i = t.get("impression_count") or 0
            r = t.get("reply_count") or 0
            fmt = "reply" if _is_reply(t.get("text", "")) else "orig"
            link = "+L" if _has_link(t.get("text", "")) else "  "
            snippet = re.sub(r"\s+", " ", (t.get("text") or "")[:60])
            lines.append(f"{i:>4} {l:>4} {r:>4}  {fmt}{link}  {snippet}")
        lines.append("```")
        lines.append("")

    # 7-day shipping pattern
    lines.append("## Part 3 — 7-day shipping pattern (from tracker)")
    lines.append("")
    if not ship_summary["events"]:
        lines.append("_No ship events tracked. Start using `python scripts/approve.py` "
                     "to populate the log; gap-detection improves with history._")
    else:
        from collections import Counter
        by_fmt = Counter(e["format"] for e in ship_summary["events"])
        by_lang = Counter(e["lang"] for e in ship_summary["events"])
        lines.append(f"- Total ships: {len(ship_summary['events'])}")
        lines.append(f"- Format mix: {dict(by_fmt)}")
        lines.append(f"- Language mix: {dict(by_lang)}")
    lines.append("")

    # Diagnosis
    lines.append("## Part 4 — Diagnosis")
    lines.append("")
    findings = []
    if lr < 0.3 and n >= 3:
        findings.append(
            f"**Resonance gap:** {lr:.2f}% like-per-impression vs healthy baseline of 0.5-2%. "
            "Transformer's first-show prediction over-fires, sees no follow-through, then "
            "self-corrects downward. All 19 positive engagement actions feed into the next-show "
            f"score (`weighted_scorer.rs:49-67`); you're hitting near-zero on most posts."
        )
    if reply_ratio > 30 and n >= 3:
        findings.append(
            f"**Reply ratio at {reply_ratio:.0f}%:** Replies route to the recipient's mentions surface, "
            "not your followers' For-You. Borrowed-reach, not earned-reach. The single biggest "
            "lever you control directly."
        )
    if n >= 4:
        findings.append(
            f"**Burst-posting ({n}/24h):** Triggers exponential `AuthorDiversityDecay` "
            "(`ranking_scorer.rs:186-187`). Each marginal post gets multiplied by `decay_factor^position`. "
            f"Your post #{n} got a fraction of post #2's reach to the same viewer."
        )
    if stats["en"] == 0 and stats["cn"] >= 3:
        findings.append(
            "**Single-language ceiling:** Tweets are routed in language pools. CN pool is "
            "much smaller than EN. Zero EN posts caps your candidate viewer set."
        )
    if not any(len((data.get("own_tweets") or [{}])[0].get("text", "")) > 1000 for _ in [None]):
        # crude: no longform check via tweet text length
        pass
    if not findings:
        findings.append("No critical findings. Holding pattern is fine; iterate on hook quality.")
    for f_ in findings:
        lines.append(f"- {f_}")
    lines.append("")

    # Suggestions
    lines.append("## Part 5 — Suggestions to lift impressions (ranked)")
    lines.append("")
    suggestions = _build_suggestions(stats, ship_summary)
    for tier, items in suggestions:
        lines.append(f"### {tier}")
        lines.append("")
        for label, body in items:
            lines.append(f"**{label}**")
            lines.append("")
            lines.append(body)
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        f"_Re-run anytime: `python scripts/diagnose.py`. "
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}._"
    )
    return "\n".join(lines)


def _build_suggestions(stats: dict, ship_summary: dict) -> list[tuple[str, list[tuple[str, str]]]]:
    """Return [(tier_header, [(label, body), ...])] sorted by expected impact."""
    n = stats["n"]
    reply_ratio = stats["reply_ratio"] * 100
    tier1: list[tuple[str, str]] = []
    tier2: list[tuple[str, str]] = []
    tier3: list[tuple[str, str]] = []

    if reply_ratio > 30 and n >= 3:
        tier1.append((
            "S1. Cut reply ratio from "
            f"{reply_ratio:.0f}% to <30%.",
            "Replies route to the recipient's mentions surface, not your followers' For-You. "
            "Cap at 2 replies/24h (already enforced in `approve.py --override` to bypass). "
            "Expected: +30-40% own-feed impressions over 2 weeks.",
        ))
    from collections import Counter
    by_fmt = Counter(e["format"] for e in ship_summary["events"]) if ship_summary["events"] else Counter()
    if by_fmt.get("thread", 0) < 1:
        tier1.append((
            "S2. Ship 1 thread/week.",
            "Threads = one `AuthorDiversityDecay` author event (`ranking_scorer.rs:195-196`); "
            "compound engagement via `conversation_id`; `CONT_DWELL_TIME_WEIGHT` rewards time-on-content. "
            "Typically 5-10× standalone reach.",
        ))
    if stats["en"] == 0 and stats["cn"] >= 3:
        tier1.append((
            "S3. Add 1 EN post/day.",
            "Language-pool routing — CN pool ceiling is finite, EN is the largest. "
            "Even 1-2 EN originals/day opens a much larger candidate viewer set.",
        ))

    if by_fmt.get("video", 0) < 1:
        tier2.append((
            "S4. Ship 1 video/week, > `MIN_VIDEO_DURATION_MS`.",
            "`VQV_WEIGHT` is positive (`weighted_scorer.rs:72-80`); short clips zero out. "
            "Less crowded lane. Screen recordings of your workflow demos qualify.",
        ))
    if by_fmt.get("longform", 0) < 1:
        tier2.append((
            "S5. 1 Premium long-form post/week.",
            "Premium boost magnitude unknown but real per source. Long-form is a distinct surface; "
            "additive, not cannibalizing. Reuse content from a thread that performed.",
        ))
    tier2.append((
        "S6. Specialize for 2 weeks straight.",
        "`HashConfig.num_author_hashes=2` (`phoenix/recsys_model.py:99`) — the transformer "
        "learns 'this author = topic X' embeddings only if your content is topically consistent.",
    ))

    if n >= 4:
        tier3.append((
            "S7. Hard cap: 3 standalone posts/24h.",
            "Already enforced in `approve.py`. `AuthorDiversityDecay` formula at "
            "`ranking_scorer.rs:186-187` is exponential; post #4+ gets fractional reach.",
        ))
    tier3.append((
        "S8. Stop low-signal politeness replies.",
        "Each one burns a daily slot and adds to decay count. Like instead of reply.",
    ))
    tier3.append((
        "S9. Re-fetch metrics on 24-80h tweets weekly.",
        "Posts stay in candidate pool up to `POST_AGE_MAX_MINUTES=4800` = 80h "
        "(`phoenix/recsys_model.py:33`). Sunday's `weekly_review.py` does this automatically.",
    ))

    out: list[tuple[str, list[tuple[str, str]]]] = []
    if tier1:
        out.append(("Tier 1 — Highest leverage", tier1))
    if tier2:
        out.append(("Tier 2 — Format moves", tier2))
    if tier3:
        out.append(("Tier 3 — Behavioral", tier3))
    return out


def main() -> int:
    src = _latest_pulse_data()
    if not src:
        print(f"No pulse data found in {PULSE_DIR} (looking for _pulse_data_*.json).")
        print("Run `X_CONTROL_DUMP_DATA=1 python scripts/monitor.py` first.")
        return 2
    data = json.loads(src.read_text())
    stats = _own_stats(data)
    ship_summary = {"events": tracker.events_in_last(24 * 7)}
    text = render(data, stats, ship_summary)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
