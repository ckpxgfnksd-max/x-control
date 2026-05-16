"""Render PulseData to the markdown digest format consumed by /x-brief."""
from __future__ import annotations

import re  # noqa: I001
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .monitor import PulseData


def _short(text: str, n: int = 220) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def _engagement_score(t: dict) -> int:
    # Impressions when present; otherwise likes-weighted proxy.
    if t.get("impression_count"):
        return int(t["impression_count"])
    return int(t.get("like_count", 0)) * 10 + int(t.get("retweet_count", 0)) * 30 + int(t.get("reply_count", 0)) * 5


def _own_tweet_features(tweets: list[dict]) -> dict:
    """Lightweight feature extraction for own tweets — patterns /x-brief can balance."""
    if not tweets:
        return {}
    cn = sum(1 for t in tweets if re.search(r"[一-鿿]", t.get("text", "")))
    en = len(tweets) - cn
    replies = sum(1 for t in tweets if t.get("text", "").lstrip().startswith("@"))
    originals = len(tweets) - replies
    with_link = sum(1 for t in tweets if re.search(r"https?://|t\.co/", t.get("text", "")))
    avg_likes = sum((t.get("like_count", 0) or 0) for t in tweets) / max(len(tweets), 1)
    return {
        "cn": cn, "en": en,
        "replies": replies, "originals": originals,
        "with_link": with_link,
        "avg_likes": avg_likes,
    }


def _own_tweet_line(t: dict, own: str) -> str:
    likes = t.get("like_count", 0) or 0
    rts = t.get("retweet_count", 0) or 0
    reps = t.get("reply_count", 0) or 0
    imps = t.get("impression_count", 0) or 0
    # Compact engagement: drop zero fields, drop impressions if 0
    bits = []
    if likes: bits.append(f"{likes}❤")
    if rts: bits.append(f"{rts}🔁")
    if reps: bits.append(f"{reps}💬")
    if imps: bits.append(f"{imps:,}👁")
    if not bits: bits.append("0 engagement")
    return (
        f"- `{' '.join(bits)}` "
        f"[{_short(t.get('text', ''), 130)}](https://x.com/{own}/status/{t['id']})"
    )


def _today_decision(data: "PulseData") -> list[str]:
    """1-paragraph TL;DR: what should you DO today, derived from the signals.
    Includes specific @handles and tweet IDs so /x-brief can act without scrolling.
    """
    parts: list[str] = []
    own_count = len(data.own_tweets)
    burst = own_count >= 4
    trapped = [
        t for t in data.own_tweets
        if (t.get("reply_count", 0) or 0) >= 3 and (t.get("like_count", 0) or 0) <= 1
    ]
    mentions = data.own_mentions.get("data") if isinstance(data.own_mentions, dict) else None
    includes = data.own_mentions.get("includes", {}) if isinstance(data.own_mentions, dict) else {}
    user_lookup = {u["id"]: u for u in includes.get("users", [])} if includes else {}
    mention_count = len(mentions) if mentions else 0

    # 1) Post-budget decision
    if burst:
        parts.append(
            f"**Hold standalone posts.** {own_count} in 24h — `AuthorDiversityDecay` "
            "(`home-mixer/scorers/ranking_scorer.rs:195-196`) biting. "
            "Reply or thread instead (a thread is one author event)."
        )
    elif own_count == 0:
        parts.append(
            "**Open window.** No posts today — fresh "
            "`AuthorDiversityDecay` slot (`ranking_scorer.rs:195`)."
        )
    else:
        remaining = max(0, 3 - own_count)
        parts.append(
            f"**Post budget:** {remaining} standalone posts left before "
            f"`AuthorDiversityDecay` (`ranking_scorer.rs:195`) penalty (4+ in 24h)."
        )

    # 2) OON-trapped — name a specific tweet
    if trapped:
        own = data.own_handle or "you"
        worst = max(trapped, key=lambda t: t.get("reply_count", 0))
        url = f"https://x.com/{own}/status/{worst['id']}"
        parts.append(
            f"**{len(trapped)} OON-trapped tweet{'s' if len(trapped) > 1 else ''}** below — "
            f"worst: [{worst.get('reply_count', 0)} replies / {worst.get('like_count', 0)} likes]({url}). "
            "Argument tree with no in-network amplification → "
            "`OON_WEIGHT_FACTOR` (`oon_scorer.rs:21`) suppression. Delete or quote-reframe."
        )

    # 3) Top mention to reply to — named
    if mentions:
        scored = [
            (
                (user_lookup.get(m.get("author_id"), {}).get("public_metrics") or {}).get("followers_count", 0),
                m,
                user_lookup.get(m.get("author_id"), {}),
            )
            for m in mentions
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        top_followers, top_m, top_author = scored[0]
        uname = top_author.get("username", "unknown")
        snippet = _short(top_m.get("text", ""), 80)
        parts.append(
            f"**Top reply target:** @{uname} ({top_followers:,} followers) — \"{snippet}\". "
            f"({mention_count} total mentions unreplied.)"
        )

    # 4) Viral KOL angle to quote
    if data.viral_posts:
        v = data.viral_posts[0]
        t = v["tweet"]
        parts.append(
            f"**Viral KOL to quote:** @{v['handle']} "
            f"({t.get('like_count', 0)}❤ {t.get('reply_count', 0)}💬) — "
            f"\"{_short(t.get('text',''), 100)}\". Manual quote on x.com."
        )

    # 5) Tomorrow's content gap — derived from today's pattern rollup
    feats = _own_tweet_features(data.own_tweets)
    if feats:
        gaps = []
        if feats["en"] == 0 and feats["cn"] >= 3:
            gaps.append("0 EN originals today — brief should propose ≥1 EN long-form")
        if feats["originals"] == 0 and feats["replies"] >= 3:
            gaps.append("all replies today — brief should propose ≥1 original thread")
        if feats["with_link"] == 0 and len(data.own_tweets) >= 3:
            gaps.append("0 link-bearing posts (reach -30-50% folklore aside, links lower OON-trapped risk per `oon_scorer.rs:21` since they pull in-network clicks)")
        if feats["avg_likes"] < 1 and len(data.own_tweets) >= 3:
            gaps.append("avg <1❤ across posts — angle is missing in-network resonance; brief should index harder on your distinctive ex-Binance angle")
        if gaps:
            parts.append("**Tomorrow's gap:** " + "; ".join(gaps) + ".")

    # 6) 7-day format gaps (algo: VQV reward + Premium long-form lane)
    try:
        from .tracker import events_in_last
        from collections import Counter
        week = events_in_last(24 * 7)
        if week:
            fmt = Counter(e["format"] for e in week)
            week_gaps = []
            if fmt.get("video", 0) == 0:
                week_gaps.append("0 video posts in 7d — `VQV_WEIGHT` (`weighted_scorer.rs:72-80`) is an unused lane")
            if fmt.get("longform", 0) == 0:
                week_gaps.append("0 long-form posts in 7d — Premium long-form is a distinct surface")
            if fmt.get("thread", 0) == 0:
                week_gaps.append("0 threads in 7d — threads = one author event, 5-10× typical reach")
            if week_gaps:
                parts.append("**7-day format gap:** " + "; ".join(week_gaps) + ".")
    except Exception:
        pass  # tracker may not exist yet on first run

    return parts


def _block_status(data: "PulseData") -> str:
    """One-line block-level status: own/mentions/KOLs/viral, ✓ or ✗ with counts.
    KOL counter splits successful vs failed-fetch handles."""
    mentions = data.own_mentions.get("data") if isinstance(data.own_mentions, dict) else None
    mention_count = len(mentions) if mentions else 0
    own_count = len(data.own_tweets)
    kol_count = len(data.kol_rows)
    viral_count = len(data.viral_posts)
    # Item-level KOL failures look like "@<handle>: ..." in data.failures
    kol_failed = sum(1 for f in data.failures if f.lstrip().startswith("@"))
    failure_text = " ".join(data.failures).lower()
    # Own block fails if any of: explicit "own block" error, OAuth error, cost-cap during own
    own_fail = any(k in failure_text for k in ("own block", "oauth", "official."))
    own_ok = "✗" if (not own_count and own_fail) else "✓"
    mentions_fail = any(k in failure_text for k in ("me_mentions", "mentions"))
    mentions_ok = "✗" if (not mention_count and mentions_fail) else "✓"
    kol_fail = any(k in failure_text for k in ("kol block", "last30days", "bird"))
    kol_ok = "✗" if (not kol_count and kol_fail) else "✓"
    kol_str = f"KOLs {kol_ok} {kol_count}"
    if kol_failed:
        kol_str += f" ({kol_failed} failed)"
    parts = [
        f"own {own_ok} {own_count}",
        f"mentions {mentions_ok} {mention_count}",
        kol_str,
        f"viral {'✓' if viral_count else '∅'} {viral_count}",
    ]
    return " · ".join(parts)


def render(data: "PulseData") -> str:
    lines: list[str] = []
    lines.append(f"# X Pulse — {data.today.isoformat()}")
    lines.append("")
    lines.append(f"`status: {_block_status(data)}`")
    lines.append("")

    # ---- warning banner at top when block-level failures exist ----
    if data.failures:
        # Categorize: block-level (own/KOL/auth) vs item-level (single handle)
        block_level = [
            f for f in data.failures
            if any(tag in f for tag in ("OAuth", "official", "last30days:", "cost cap", "own block", "KOL block"))
        ]
        if block_level:
            lines.append("> ⚠️ **Run had failures — partial pulse.** See footer for details.")
            for f in block_level[:3]:
                lines.append(f"> - {f.splitlines()[0][:160]}")
            lines.append("")

    # ---- TL;DR: today's posting decision ----
    decision = _today_decision(data)
    if decision:
        lines.append("## Today's posting decision")
        for d in decision:
            lines.append(f"- {d}")
        lines.append("")

    if data.notes:
        for n in data.notes:
            lines.append(f"> {n}")
        lines.append("")

    # ---- mentions promoted to top (replies are higher-leverage than posts) ----
    mentions = data.own_mentions.get("data") if isinstance(data.own_mentions, dict) else None
    includes = data.own_mentions.get("includes", {}) if isinstance(data.own_mentions, dict) else {}
    user_lookup = {u["id"]: u for u in includes.get("users", [])} if includes else {}
    if mentions:
        lines.append("## Unanswered mentions — ranked by reach × recency")
        from datetime import datetime as _dt, timezone as _tz
        import math as _math
        now = _dt.now(_tz.utc)
        scored = []
        for m in mentions:
            author = user_lookup.get(m.get("author_id"), {})
            followers = (author.get("public_metrics") or {}).get("followers_count", 0)
            age_hours = 12.0
            ts = m.get("created_at")
            if ts:
                try:
                    dt = _dt.fromisoformat(str(ts).replace("Z", "+00:00"))
                    age_hours = (now - dt).total_seconds() / 3600.0
                except (ValueError, TypeError):
                    pass
            recency = _math.exp(-age_hours / 24.0)
            score = _math.log10(max(followers, 1) + 1) * recency
            scored.append((score, followers, age_hours, m, author))
        scored.sort(key=lambda x: x[0], reverse=True)
        shown = 3 if len(scored) > 4 else len(scored)
        for score, followers, age_h, m, author in scored[:shown]:
            uname = author.get("username", "unknown")
            tid = m.get("id")
            urgency = "🔴" if age_h < 6 else ("🟡" if age_h < 24 else "🟢")
            age_str = f"{age_h:.0f}h" if age_h < 48 else f"{age_h/24:.0f}d"
            lines.append(
                f"- {urgency} **@{uname}** ({followers:,} • {age_str} ago) — "
                f"[{_short(m.get('text', ''), 130)}](https://x.com/{uname}/status/{tid})"
            )
        if len(scored) > shown:
            oldest = scored[-1]
            oldest_h = oldest[2]
            oldest_str = f"{oldest_h:.0f}h" if oldest_h < 48 else f"{oldest_h/24:.0f}d"
            lines.append(f"- _+ {len(scored) - shown} more, oldest {oldest_str} ago_")
        lines.append("")

    # ---- own account ----
    lines.append("## Your account (last 24h, via official API)")
    own = data.own_handle or "you"
    if not data.own_tweets:
        lines.append("_No tweets in the last 24h, or own block failed (see footer)._")
    else:
        # Pattern rollup — brief uses this to balance tomorrow's mix
        feats = _own_tweet_features(data.own_tweets)
        if feats:
            lines.append(
                f"_Pattern: {feats['cn']} CN + {feats['en']} EN, "
                f"{feats['replies']} replies + {feats['originals']} originals, "
                f"{feats['with_link']} with links. Avg {feats['avg_likes']:.1f}❤/post._"
            )
            lines.append("")
        ranked = sorted(data.own_tweets, key=_engagement_score, reverse=True)
        lines.append("### Top performers")
        for t in ranked[:3]:
            lines.append(_own_tweet_line(t, own))

        # OON-trapped signal: replies present but no in-network amplification.
        # Per xai-org/x-algorithm OON_WEIGHT_FACTOR: out-of-network posts are
        # structurally penalized; the only escape is fast in-network engagement
        # (likes from your existing followers). High reply + zero like = argument
        # tree without in-network amplification = trapped in OON.
        trapped = [
            t for t in ranked
            if (t.get("reply_count", 0) or 0) >= 3
            and (t.get("like_count", 0) or 0) <= 1
        ]
        if trapped:
            lines.append("")
            lines.append("### ⚠ OON-trapped tweets (replies ≥ 3, likes ≤ 1)")
            lines.append("_Argument-style replies with no in-network amplification → "
                         "`OON_WEIGHT_FACTOR` (`home-mixer/scorers/oon_scorer.rs:21`) "
                         "suppression. Consider deleting or quote-reframing._")
            for t in trapped:
                lines.append(_own_tweet_line(t, own))

        # Burst tracker (author-diversity-decay context)
        own_count_24h = len(data.own_tweets)
        if own_count_24h >= 4:
            lines.append("")
            lines.append(f"### ⚠ Burst window: {own_count_24h} posts in last 24h")
            lines.append("_`AuthorDiversityDecay` + `AuthorDiversityFloor` "
                         "(`home-mixer/scorers/ranking_scorer.rs:195-196`) penalize the "
                         "same author shown repeatedly to the same viewer. Threads = "
                         "one author event; standalone bursts compound the penalty._")

        if len(ranked) > 3:
            lines.append("")
            lines.append("### Topics to NOT repeat tomorrow (bottom-of-window)")
            for t in ranked[-min(3, len(ranked) - 3):]:
                lines.append(_own_tweet_line(t, own))
    lines.append("")

    # ---- kol posting velocity ----
    lines.append("## KOL posting velocity (via bird-search / last30days cookies)")
    if not data.kol_rows:
        lines.append("_KOL block unavailable (see footer)._")
    else:
        sortable = [r for r in data.kol_rows if r.get("velocity_ratio") is not None]
        baseline_only = [r for r in data.kol_rows if r.get("velocity_ratio") is None]
        sortable.sort(key=lambda r: r.get("velocity_ratio") or 0, reverse=True)
        if sortable:
            lines.append("| handle | category | tweets/24h | prior | Δ | ratio | flag |")
            lines.append("|---|---|---:|---:|---:|---:|:---:|")
            for r in sortable:
                flag = "⚡" if r["flagged"] else ""
                sign = "+" if (r["velocity_delta"] or 0) >= 0 else ""
                lines.append(
                    f"| @{r['handle']} | {r.get('category', '?')} | {r['tweet_count_24h']} | "
                    f"{r['prev_count']} | {sign}{r['velocity_delta']} | "
                    f"{r['velocity_ratio']:.2f}× | {flag} |"
                )
        if baseline_only:
            if sortable:
                lines.append("")
            active = [r for r in baseline_only if r["tweet_count_24h"] > 0]
            quiet = [r for r in baseline_only if r["tweet_count_24h"] == 0]
            if active:
                lines.append("_Baseline (no prior snapshot — deltas available tomorrow):_")
                active.sort(key=lambda r: r["tweet_count_24h"], reverse=True)
                for r in active:
                    lines.append(f"- @{r['handle']}: {r['tweet_count_24h']} tweets/24h")
            if quiet:
                # Aggregate by category when many; otherwise list names
                from collections import Counter
                cat_counts = Counter(r.get("category", "?") for r in quiet)
                if len(quiet) >= 5 and len(cat_counts) >= 2:
                    by_cat = ", ".join(f"{n} {c}" for c, n in cat_counts.most_common())
                    lines.append(f"_Quiet last 24h ({len(quiet)}): {by_cat}_")
                else:
                    quiet_handles = ", ".join(f"@{r['handle']}" for r in quiet)
                    lines.append(f"_Quiet last 24h ({len(quiet)}):_ {quiet_handles}")
    lines.append("")

    # ---- viral posts ----
    lines.append("## Viral KOL posts (last 24h)")
    lines.append("_Threshold: ≥500 likes OR ≥100 replies. (Bird doesn't surface quote counts.)_")
    if not data.viral_posts:
        lines.append("_None hit the threshold._")
    else:
        data.viral_posts.sort(
            key=lambda v: v["tweet"].get("like_count", 0) + v["tweet"].get("reply_count", 0),
            reverse=True,
        )
        for v in data.viral_posts:
            t = v["tweet"]
            lines.append("")
            lines.append(
                f"### @{v['handle']} — "
                f"{t.get('like_count', 0)}❤ "
                f"{t.get('retweet_count', 0)}🔁 "
                f"{t.get('reply_count', 0)}💬"
            )
            lines.append(f"[{_short(t.get('text', ''), 240)}]({v['url']})")
    lines.append("")

    # ---- weekly tracker rollup ----
    try:
        from .tracker import events_in_last
        from collections import Counter
        week = events_in_last(24 * 7)
        if week:
            fmt = Counter(e["format"] for e in week)
            lang = Counter(e["lang"] for e in week)
            lines.append("## 7-day ship log")
            fmt_str = " · ".join(f"{n} {k}" for k, n in fmt.most_common())
            lang_str = " · ".join(f"{n} {k}" for k, n in lang.most_common())
            lines.append(f"_{len(week)} ships this week — format: {fmt_str} | lang: {lang_str}_")
            # Specialty drift: Shannon entropy of first-word-of-tweet (proxy for topic)
            import re as _re, math as _math
            firsts = []
            for e in week:
                # No tweet text in event; use char_count buckets as a crude proxy
                # Better: future version stores topic tags. For now skip if no text.
                pass
            lines.append("")
    except Exception:
        pass

    # ---- footer ----
    lines.append("---")
    lines.append("## Run metadata")
    lines.append("")
    lines.append("```")
    lines.append(data.cost_summary)
    lines.append("```")
    if data.failures:
        lines.append("")
        lines.append("### Warnings")
        for f in data.failures:
            lines.append(f"- {f}")
    lines.append("")
    return "\n".join(lines)
