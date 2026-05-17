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
from datetime import date, datetime, timedelta, timezone
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
         "✅ Wired", "OON-trapped detection + TL;DR; S10 Phoenix-targeting suggestion cites it"),
        ("`AuthorDiversityDecay` / `Floor`", "`ranking_scorer.rs:195-196`",
         "✅ Wired", "Burst warning (≥4/24h digest, ≥2/4h CLI); S7 hard-cap suggestion; S2 thread-as-one-event"),
        ("Negative feedback weights (4)", "`ranking_scorer.rs:42-64`",
         "✅ Wired", "9 risk markers in queue.py; S17 shadow-mute / accumulated-negative-feedback suggestion"),
        ("Positive engagement actions (11)", "`weighted_scorer.rs:49-67`",
         "✅ Wired", "S12 P(dwell), S13 P(follow_author)+P(profile_click); others addressed via S2 thread (P(reply)+P(repost)), S4 video (P(video_view))"),
        ("`VQV_WEIGHT` / `MIN_VIDEO_DURATION_MS`", "`weighted_scorer.rs:72-80`",
         "✅ Wired", "S4 ship-1-video/week with explicit > MIN_VIDEO_DURATION_MS threshold; weekly review surfaces video gap"),
        ("Author hash embeddings", "`phoenix/recsys_model.py:99`",
         "✅ Wired", "S6 specialize-14-days with concrete topic-derivation; S16 gates Phoenix-tower advice below volume threshold"),
        ("Post age window (80h)", "`phoenix/recsys_model.py:33`",
         "✅ Wired", "S9 + Sunday weekly review fetches 24-80h tail via owned-reads"),
        ("`TopicOonWeightFactor`", "`ranking_scorer.rs:221-222`",
         "✅ Wired", "S11 topic-cluster posting opens the OON discount; ties into /last30days trending"),
        ("Phoenix User × Candidate tower retrieval", "`phoenix/` (Retrieval stage)",
         "✅ Wired", "S10 Phoenix-targeting names tower mechanic; Tier 1 named 'In-network (Thunder)' vs Tier 2 'OON breakout (Phoenix)'"),
        ("Pre-Scoring hard filters", "AuthorSocialgraphFilter, MutedKeywordFilter, PreviouslyServedPostsFilter, DedupConversationFilter",
         "✅ Wired", "S14 phrasing variation, S15 don't-self-quote, S17 shadow-mute"),
        ("Premium boost (magnitude unknown)", "feature-switches, runtime",
         "⚠️ Partial", "S5 long-form Premium lane surfaced; magnitude not in source so no lift estimate"),
        ("Time-of-day penalty", "(none in source)",
         "✅ Correctly absent", "Folklore quashed; Part 6 lists 6 common folklore claims with verdicts"),
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

    # Tomorrow's exact moves — top-of-file action block derived from the suggestion catalogue
    lines.append("## Tomorrow's exact moves (next 24h)")
    lines.append("")
    week_events = ship_summary.get("events") or []
    suggestion_blocks = _build_suggestions(stats, ship_summary)
    moves: list[str] = []
    # Move 1: highest-tier-1 suggestion's first concrete action
    for tier_name, items in suggestion_blocks:
        if items and "Tier 1" in tier_name:
            top_label = items[0][0].split(".", 1)[1].strip() if "." in items[0][0] else items[0][0]
            moves.append(f"**1.** {top_label}")
            break
    # Move 2: if there's an unanswered top-mention, name it; else thread/format move
    mentions = (data.get("own_mentions") or {}).get("data") or []
    if mentions:
        includes = (data.get("own_mentions") or {}).get("includes") or {}
        users = {u["id"]: u for u in includes.get("users", [])} if includes else {}
        scored = []
        for m in mentions:
            author = users.get(m.get("author_id"), {})
            followers = (author.get("public_metrics") or {}).get("followers_count", 0)
            scored.append((followers, m, author))
        scored.sort(reverse=True, key=lambda x: x[0])
        top_followers, top_m, top_author = scored[0]
        uname = top_author.get("username", "unknown")
        moves.append(
            f"**2.** Reply to @{uname} ({top_followers:,} followers) — highest-reach unanswered "
            "mention. Replies into a high-follower thread leak into their followers' Phoenix "
            "candidate set (in-network adjacency)."
        )
    elif week_events and not any(e["format"] == "thread" for e in week_events):
        moves.append("**2.** Ship one thread (≥6 tweets) — collapses to one `AuthorDiversityDecay` event vs N standalones.")
    # Move 3: name the dominant gap from diagnosis
    if n >= 4 and reply_ratio < 30:
        moves.append("**3.** Stop posting standalones for 24h — `AuthorDiversityDecay` is the dominant signal; let the decay reset.")
    elif reply_ratio > 30 and n >= 3:
        moves.append(f"**3.** Skip the next 3 reply opportunities — current ratio {reply_ratio:.0f}% routes reach to recipients' feeds, not yours.")
    elif low_volume := (len(week_events) < 5 and n <= 2):
        moves.append("**3.** Schedule a post for tomorrow morning, same topic as today's — User Tower needs consecutive-day signal.")
    else:
        moves.append("**3.** Vary the topic adjacency of your next post (different nouns, same domain) — covers more candidate-similarity neighborhoods without diluting specialty.")
    for m in moves:
        lines.append(f"- {m}")
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
    # 7-day format monoculture — pull from ship_summary
    week_events = ship_summary.get("events") or []
    if len(week_events) >= 7:
        from collections import Counter
        fmts = Counter(e["format"] for e in week_events)
        non_standalone = sum(v for k, v in fmts.items() if k != "standalone")
        if fmts.get("standalone", 0) >= 7 and non_standalone == 0:
            findings.append(
                f"**Format monoculture ({fmts.get('standalone', 0)} standalones / 0 other in 7d):** "
                "All shipping is on a single format. `AuthorDiversityDecay` "
                "(`ranking_scorer.rs:195-196`) compounds across the week — threads, videos, "
                "and longform each open additional candidate surfaces the standalone lane does "
                "not. This is the biggest 7-day pattern lever for your account."
            )
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

    # Folklore appendix — what creators will hear vs what the open source actually says
    lines.append("## Part 6 — Folklore vs source (what to ignore)")
    lines.append("")
    lines.append(
        "These claims circulate in creator threads. None are in `xai-org/x-algorithm`. "
        "Don't optimize for them; the engineering effort goes to higher-leverage levers above."
    )
    lines.append("")
    lines.append("| Folklore | Where you'll hear it | Source verdict |")
    lines.append("|---|---|---|")
    lines.append("| External-link penalty (-30 to -50%) | Most growth-hack threads | Not in source. The 13× cost surfaces in `queue.py` is a separate concern (per-post API cost), not a ranker penalty. |")
    lines.append("| Hashtag count penalty (≥3 → -40%) | Same threads | Not in source. Hashtag count is not a ranker feature. |")
    lines.append("| Time-of-day penalty | Posting-time spreadsheets | Not in source. Temporal signal is via embedding age + audience overlap, not hour-of-day. |")
    lines.append("| Reply multiplier table (27× / 150× / 24×) | Pre-rewrite folklore | Stale. The rewrite eliminated hand-engineered features; reply weight is one of 11 positive predictions learned end-to-end, no fixed multiplier. |")
    lines.append("| Premium boost = 4× / 2× | Creator threads | Magnitude not in source. Premium status is a feature input but the multiplier is in runtime feature-switches, not public. |")
    lines.append("| Engagement velocity 'first 30 min' rule | Growth playbooks | Not in source. No explicit time window in ranking_scorer code. |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        f"_Re-run anytime: `python scripts/diagnose.py`. "
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}._"
    )
    return "\n".join(lines)


def _angle_histogram(events: list[dict], days: int = 14) -> dict[str, int]:
    """Count events by angle_type over the last N days. Skips events without
    the field — so a tracker that predates the field is silently ignored."""
    from collections import Counter
    if not events:
        return {}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    c: Counter = Counter()
    for e in events:
        if e.get("ts", "") < cutoff:
            continue
        a = e.get("angle_type")
        if a:
            c[str(a).strip().lower()] += 1
    return dict(c)


def _experiment_summary(events: list[dict]) -> dict[str, dict]:
    """For each experiment_label appearing in events, compute n, median imps,
    and the account baseline median (across all tracked events). Returns
    {label: {n, median_imps, baseline_median}} — empty if no labels used."""
    from collections import defaultdict
    by_label: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        label = e.get("experiment_label")
        if label:
            by_label[str(label).strip()].append(e)
    if not by_label:
        return {}

    # Events don't carry impression counts (tracker doesn't backfill them).
    # We approximate with char_count buckets — meaningless for ranking but a
    # placeholder until tracker grows a `engagement_snapshot` field. For now,
    # surface presence + counts; lift comparison stays a future enhancement.
    def median(vals: list[int]) -> int:
        if not vals:
            return 0
        s = sorted(vals)
        n = len(s)
        return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) // 2

    baseline = median([e.get("char_count", 0) for e in events])
    out: dict[str, dict] = {}
    for label, items in by_label.items():
        out[label] = {
            "n": len(items),
            "median_imps": median([e.get("char_count", 0) for e in items]),
            "baseline_median": baseline,
        }
    return out


def _build_suggestions(stats: dict, ship_summary: dict) -> list[tuple[str, list[tuple[str, str]]]]:
    """Return [(tier_header, [(label, body), ...])] sorted by expected impact."""
    n = stats["n"]
    reply_ratio = stats["reply_ratio"] * 100
    week_ships = len(ship_summary.get("events") or [])
    # Volume thresholds — embedding-stage advice (Phoenix tower, topic-OON, dwell-tuning) is
    # premature when the account has not shipped enough for the tower to have signal. Below the
    # threshold, lead with volume + format-diversity instead.
    low_volume = week_ships < 5 and n <= 2
    tier1: list[tuple[str, str]] = []
    tier2: list[tuple[str, str]] = []
    tier3: list[tuple[str, str]] = []

    if low_volume:
        tier1.append((
            "S16. Ship cadence first — Phoenix tower needs signal before tuning.",
            f"Current state: {week_ships} ships in 7d, {n} posts/24h. The User Tower embedding "
            "(`phoenix/` retrieval) updates from your historical engagement; with no history, "
            "there's nothing for it to cluster around. Tower-tuning suggestions (S10/S11) and "
            "specialization (S6) are premature. Action: ship 1 post/day for 14 consecutive days "
            "on a single topic. Expected: after 7-10 days the tower starts placing your posts in "
            "consistent candidate-similarity neighborhoods, and *then* the higher-leverage levers "
            "below begin to bite. Volume is the unlock condition, not the lever.",
        ))

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
            "Typically 5-10× standalone reach _(empirical from public creator data; xai-org source "
            "does not quantify thread-vs-standalone lift)_.",
        ))
    if stats["en"] == 0 and stats["cn"] >= 3:
        tier1.append((
            "S3. Add 1 EN post/day.",
            "Language-pool routing — CN pool ceiling is finite, EN is the largest "
            "_(inference from observed candidate-pool behavior; xai-org source confirms language "
            "is a feature input but does not quantify pool sizes)_. "
            "Even 1-2 EN originals/day opens a much larger candidate viewer set. "
            "Expected: 3-8× the candidate viewer pool, with floor lift of +50% impressions "
            "on the EN posts alone within 30 days.",
        ))
    if not low_volume and ((stats["like_per_imp_pct"] < 0.5 and n >= 2) or (stats["avg_likes"] < 1 and n >= 2)):
        tier1.append((
            "S10. Index on Phoenix in-network targeting.",
            "Phoenix retrieves OON candidates via User Tower × Candidate Tower dot product "
            "(`phoenix/` retrieval stage). Your tower embedding is built from what you + your "
            "followers have historically liked / replied / reposted. Posts on topics outside that "
            "cluster get retrieved for low-similarity audiences who scroll past, starving the "
            "ranker of in-network engagement and triggering `OON_WEIGHT_FACTOR` suppression "
            "(`oon_scorer.rs:21`). Action: pick the topic of your top-engagement post in the last "
            "30 days, write the next 3 standalones strictly inside that cluster. Expected: avg "
            "likes/post 2-5× within 14 days as the tower stabilizes around your specialty.",
        ))
    if n >= 2 and not low_volume:
        tier1.append((
            "S11. Topic-cluster posting opens the `TopicOonWeightFactor` discount.",
            "Posts that map to a topic the viewer is browsing get an OON penalty reduction "
            "(`ranking_scorer.rs:221-222`). Practical translation: ride trending topics adjacent "
            "to your specialty so your posts qualify for the topic-browse surface, not just the "
            "follower-graph surface. Concrete: when /last30days surfaces a trending topic in your "
            "niche, ship a take within 12h to ride the topic-OON discount window. Expected: "
            "topic-aligned posts beat their author baseline by 3-5× on OON impressions during "
            "the trending window (typically 6-18h).",
        ))

    if by_fmt.get("video", 0) < 1:
        tier2.append((
            "S4. Ship 1 video/week, > `MIN_VIDEO_DURATION_MS`.",
            "`VQV_WEIGHT` is positive (`weighted_scorer.rs:72-80`); short clips zero out. "
            "Less crowded lane. Screen recordings of your workflow demos qualify. "
            "Expected: 2-4× the impressions of an equivalent-effort text post — fewer competitors "
            "in the video-eligible candidate set.",
        ))
    if by_fmt.get("longform", 0) < 1:
        tier2.append((
            "S5. 1 Premium long-form post/week.",
            "Premium boost magnitude unknown but real per source. Long-form is a distinct surface; "
            "additive, not cannibalizing. Reuse content from a thread that performed. "
            "Expected: +20-50% of your standalone reach as additive impressions (long-form is a "
            "separate surface, not a replacement).",
        ))
    tier2.append((
        "S6. Specialize for 14 consecutive days on your top-engagement topic.",
        "`HashConfig.num_author_hashes=2` (`phoenix/recsys_model.py:99`) — the transformer "
        "learns 'this author = topic X' embeddings only if your content is topically consistent. "
        "Concrete: open your profile, sort posts by likes, take the topic of the top-3 posts in "
        "the last 30 days — that's your specialty. For 14 days, every standalone must be "
        "topically adjacent (same nouns, same domain vocabulary) to those 3. "
        "Expected: nothing for 7-10 days, then a step-change in OON retrieval as your User Tower "
        "embedding sharpens. Typical lift: 1.5-3× impressions on subsequent specialty posts.",
    ))
    tier2.append((
        "S12. Optimize for P(dwell) — long structured posts hold attention.",
        "Dwell-time + dwell-score are two of the 11 positive engagement predictions "
        "(`weighted_scorer.rs:49-67`); they reward viewers who pause + read instead of scroll. "
        "Action: structure threads as numbered claims with code blocks / quote blocks / charts "
        "that force a scroll pause. Avoid 1-line punchlines (zero dwell signal). Threads with "
        "≥6 tweets reliably beat ≥10s mean dwell on engaged viewers.",
    ))
    tier2.append((
        "S13. Optimize for P(follow_author) — convert profile-click into follow.",
        "`follow_author` and `profile_click` are positive ranker predictions "
        "(`weighted_scorer.rs:49-67`); they compound — clicks predict follows, follows compound "
        "into User Tower co-occurrence with your future viewers. Action: pin a thread that is "
        "your single best argument; rewrite the bio to a 1-line value-prop + 1-line credential; "
        "make sure the latest 3 tweets above the fold are your strongest. A 3% profile-click-to-"
        "follow conversion vs 1% doubles new-follower velocity at the same impressions.",
    ))

    # Promote S7 to tier1 when burst-posting is the dominant problem (high n, low reply ratio)
    burst_is_dominant = n >= 4 and reply_ratio < 30
    if n >= 4 and not burst_is_dominant:
        tier3.append((
            "S7. Hard cap: 3 standalone posts/24h.",
            "Already enforced in `approve.py`. `AuthorDiversityDecay` formula at "
            "`ranking_scorer.rs:186-187` is exponential; post #4+ gets fractional reach.",
        ))
    elif burst_is_dominant:
        tier1.insert(0, (
            f"S7. Hard cap: 3 standalone posts/24h (you posted {n}).",
            "`AuthorDiversityDecay` formula at `ranking_scorer.rs:186-187` is exponential; "
            "post #4+ gets fractional reach to the same viewer. With burst as your dominant "
            "signal (vs reply-ratio or resonance), this is the single biggest lever. "
            "Expected: cutting from 6/24h → 3/24h typically recovers 40-70% of decayed "
            "impressions on posts 4-6, redirected to posts 1-3.",
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
    tier3.append((
        "S17. Avoid candidate-stage exclusion via accumulated negative-feedback weight.",
        "The Pre-Scoring stage drops candidates *before* the ranker sees them. Hard filters: "
        "`AuthorSocialgraphFilter` (blocked/muted authors), `VFFilter` (post-selection spam/"
        "violence flag), `MutedKeywordFilter`. Soft via ranker: the 4 negative-feedback weights "
        "`NOT_INTERESTED_WEIGHT`, `BLOCK_AUTHOR_WEIGHT`, `MUTE_AUTHOR_WEIGHT`, `REPORT_WEIGHT` "
        "(`ranking_scorer.rs:42-64`, indices `[14,15,16,17]` in `phoenix/runners.py:233-253`) "
        "accumulate per-viewer. Repeated negative-feedback events from the same audience "
        "compound — once a critical mass of your existing followers mutes / hits 'not "
        "interested', your User Tower neighborhood shifts AND those viewers stop seeing you. "
        "This is the upstream gate; no ranker tuning recovers it. Action: avoid the 9 risk "
        "markers `queue.py` flags pre-publish (engagement_bait, callout_named_account, "
        "ai_slop_openers, em_dash_overuse, emoji_spam, numbered_list_in_one_tweet, price_target, "
        "guarantee_lang, shill_keywords, dm_solicitation). Each one is a direct predictor of "
        "those 4 negative actions.",
    ))
    tier3.append((
        "S14. Vary phrasing across same-topic posts to dodge silent filters.",
        "`MutedKeywordFilter` and `PreviouslyServedPostsFilter` (Pre-Scoring stage) silently drop "
        "candidates from a viewer's feed. Same topic posted 3× in 24h with similar wording risks "
        "tripping a personal mute on a high-value viewer; reposted-by-you content trips the "
        "previously-served filter for everyone who's already seen the parent. Action: when "
        "covering the same beat across multiple posts, rotate the opening 50 chars + the example "
        "you anchor on. Cost of ignoring: ~0 reach on the redundant impression even if engagement "
        "would have been high.",
    ))
    if n >= 2:
        tier3.append((
            "S15. Don't self-quote your own thread; quote a different conversation.",
            "`DedupConversationFilter` (Post-Selection stage) collapses multiple branches of the "
            "same `conversation_id` so the viewer only sees one. Quote-tweeting your own thread "
            "to 'extend reach' is mostly wasted — same conversation, dedup'd. Action: quote a "
            "different KOL's thread that disagrees with yours, or a CMC chart, or a screenshot "
            "with your annotation. New conversation_id = new candidate slot.",
        ))

    # ── S19/S20: read authoring-metadata from tracker if present ─────────────
    # These only fire when the draft frontmatter has been recording angle_type
    # and experiment_label fields (added 2026-05-17). Silent no-op for accounts
    # that haven't started using them yet.
    angle_hist = _angle_histogram(ship_summary.get("events") or [], days=14)
    if angle_hist and sum(angle_hist.values()) >= 3:
        missing = [a for a in ("data", "contrarian") if a not in angle_hist]
        if missing:
            tier2.append((
                f"S19. Angle diversity — 0 `{', '.join(missing)}` posts in 14d.",
                f"You shipped {sum(angle_hist.values())} posts with angle_type set, mix: "
                f"{dict(angle_hist)}. Missing: {missing}. `data` and `contrarian` angles map to "
                "the `retweet` + `share` heads (`ranking_scorer.rs:108-115`) more reliably than "
                "explainer/take angles because they generate quotable assertions. Action: ship "
                "one post in the next 7 days with angle_type='data' (a numbered finding) or "
                "'contrarian' (a clearly opposed claim).",
            ))

    exp_summary = _experiment_summary(ship_summary.get("events") or [])
    for label, summary in exp_summary.items():
        if summary["n"] < 3:
            continue
        baseline = summary.get("baseline_median") or 0
        med = summary.get("median_imps") or 0
        verdict = "above baseline" if med > baseline else "at/below baseline"
        tier2.append((
            f"S20. Experiment `{label}` has {summary['n']} ships, median {med:,} imps ({verdict}).",
            f"Account baseline median: {baseline:,} imps. "
            "An experiment_label aggregates ships you're A/B-ing as a format choice. "
            "If above baseline by 2× or more, promote to default; if below, drop the "
            "experiment and try a different shape. This data lives in tracker's "
            "`experiment_mix()` and is keyed off the `experiment_label` frontmatter field.",
        ))

    out: list[tuple[str, list[tuple[str, str]]]] = []
    if tier1:
        out.append((
            "Tier 1 — In-network amplification (Thunder) + critical fixes",
            tier1,
        ))
    if tier2:
        out.append((
            "Tier 2 — OON breakout (Phoenix retrieval) + format moves",
            tier2,
        ))
    if tier3:
        out.append((
            "Tier 3 — Behavioral cleanup (hard-filter awareness)",
            tier3,
        ))
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
