#!/usr/bin/env python3
"""Sunday weekly review — rolls up format/language mix and re-fetches engagement
on tweets aged 24-80h (still in candidate pool per `POST_AGE_MAX_MINUTES=4800`).

Writes to ~/Documents/Last30Days/x-weekly-review-YYYY-MM-DD.md.
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.tracker import events_in_last                        # noqa: E402
from scripts.cost import CostTracker                              # noqa: E402
from scripts.clients.official import OfficialXClient, OAuthError  # noqa: E402
from scripts import queue                                         # noqa: E402

ENV_PATH = Path.home() / ".config" / "x-control" / ".env"
OUT_DIR = Path.home() / "Documents" / "Last30Days"


def _bar(n: int, max_n: int, width: int = 20) -> str:
    if max_n == 0:
        return ""
    filled = int(round(n / max_n * width))
    return "█" * filled + "░" * (width - filled)


def _format_mix_section() -> list[str]:
    events = events_in_last(24 * 7)
    if not events:
        return [
            "## 7-day ship log",
            "_No ships tracked yet — start of the weekly tracker. Approvals from this week will populate next Sunday._",
            "",
        ]
    fmt = Counter(e["format"] for e in events)
    lang = Counter(e["lang"] for e in events)
    total = len(events)
    lines = [
        "## 7-day ship log",
        f"**{total} ships** in last 7 days.",
        "",
        "### Format mix",
    ]
    max_fmt = max(fmt.values()) if fmt else 1
    for k in ("thread", "standalone", "reply", "longform", "video"):
        n = fmt.get(k, 0)
        marker = "" if n > 0 else " ← **GAP**"
        lines.append(f"- `{k:<10}` {_bar(n, max_fmt)} {n}{marker}")
    lines.append("")
    lines.append("### Language mix")
    max_lang = max(lang.values()) if lang else 1
    for k in ("cn", "en", "mixed"):
        n = lang.get(k, 0)
        marker = "" if n > 0 else " ← **GAP**"
        lines.append(f"- `{k:<10}` {_bar(n, max_lang)} {n}{marker}")
    lines.append("")
    # Gap diagnoses
    gaps: list[str] = []
    if fmt.get("thread", 0) == 0:
        gaps.append(
            "**0 threads** — threads are one author event (`AuthorDiversityDecay`) and "
            "accumulate engagement on `conversation_id`. Highest-leverage missing format."
        )
    if fmt.get("video", 0) == 0:
        gaps.append(
            "**0 video posts** — `VQV_WEIGHT` (`weighted_scorer.rs:72-80`) "
            "is positive for videos exceeding `MIN_VIDEO_DURATION_MS`. Less crowded lane."
        )
    if fmt.get("longform", 0) == 0:
        gaps.append(
            "**0 long-form** — Premium long-form is a distinct surface, not cannibalizing standalones."
        )
    if lang.get("en", 0) == 0:
        gaps.append(
            "**0 EN posts** — single-language ceiling on the CN candidate pool. "
            "Even 1-2/week opens the bigger English pool."
        )
    standalones = fmt.get("standalone", 0)
    if standalones > 14:  # > 2 per day on average
        gaps.append(
            f"**{standalones} standalones in 7d** (~{standalones/7:.1f}/day) — at or above "
            "the algo-suggested cap (3/24h). Each marginal post triggers exponential decay."
        )
    if gaps:
        lines.append("### Gaps")
        for g in gaps:
            lines.append(f"- {g}")
        lines.append("")
    return lines


def _eighty_hour_tail(client: OfficialXClient | None) -> list[str]:
    """Re-fetch engagement on own tweets aged 24-80h via owned-reads ($0.001 each)."""
    if not client:
        return []
    # Pull recent own_tweets (last 100, paginated if needed — for now just one page)
    try:
        me = client.me()
        recent = client._request(
            "GET",
            f"/2/users/{me['id']}/tweets",
            params={
                "max_results": 100,
                "tweet.fields": "public_metrics,created_at",
                "exclude": "retweets",
            },
        )
        recent.raise_for_status()
        data = recent.json().get("data", [])
    except Exception as e:
        return [f"## 80h tail check\n_Could not fetch: {e}_\n"]

    now = datetime.now(timezone.utc)
    in_window: list[dict] = []
    for t in data:
        try:
            dt = datetime.fromisoformat(t["created_at"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        age_h = (now - dt).total_seconds() / 3600.0
        if 24 < age_h <= 80:
            t["_age_h"] = age_h
            in_window.append(t)
    if not in_window:
        return ["## 80h tail check", "_No tweets in the 24-80h window._", ""]

    # Sort by current impressions, top 5
    in_window.sort(
        key=lambda t: (t.get("public_metrics") or {}).get("impression_count", 0),
        reverse=True,
    )
    lines = [
        "## 80h tail check",
        "_Tweets aged 24-80h that are still in the candidate pool (`POST_AGE_MAX_MINUTES=4800`). "
        "Ones still gaining engagement = topics worth doubling on._",
        "",
    ]
    own_handle = me.get("username", "you")
    for t in in_window[:5]:
        m = t.get("public_metrics") or {}
        text = (t.get("text") or "").replace("\n", " ")[:120]
        lines.append(
            f"- `{int(t['_age_h'])}h | "
            f"{m.get('like_count', 0)}❤ {m.get('retweet_count', 0)}🔁 "
            f"{m.get('reply_count', 0)}💬 {m.get('impression_count', 0):,}👁`  "
            f"[{text}](https://x.com/{own_handle}/status/{t['id']})"
        )
    lines.append("")
    return lines


def _decisions_block(events: list[dict], tail_lines: list[str]) -> list[str]:
    """One-line recommendations for next week, derived from gaps."""
    fmt = Counter(e["format"] for e in events) if events else Counter()
    lang = Counter(e["lang"] for e in events) if events else Counter()
    recs: list[str] = []
    if fmt.get("thread", 0) == 0:
        recs.append("Ship 1 thread this week (highest-leverage missing format).")
    elif fmt.get("thread", 0) < 2:
        recs.append("Ship a second thread this week — 2/week is the cadence target.")
    if fmt.get("video", 0) == 0:
        recs.append("Record one screen-cap video this week (Claude Code workflow demo is the easiest).")
    if fmt.get("longform", 0) == 0:
        recs.append("One Premium long-form post this week — reuse content from your best-performing thread.")
    if lang.get("en", 0) < 3 and lang.get("cn", 0) >= 3:
        recs.append("Increase EN mix — minimum 1/day.")
    standalones = fmt.get("standalone", 0)
    if standalones > 14:
        recs.append(f"Reduce standalones — currently {standalones}/7d, target ≤14 (2/day).")
    if not recs:
        recs.append("Format/language mix is healthy. Focus on hook quality + audience-topic fit.")
    return [
        "## Next week's targets",
        *(f"- {r}" for r in recs),
        "",
    ]


def main() -> int:
    load_dotenv(ENV_PATH)
    today = date.today()
    events = events_in_last(24 * 7)

    # Try to set up the official client for the 80h tail check
    client: OfficialXClient | None = None
    try:
        cost = CostTracker()
        client = OfficialXClient(
            client_id=os.environ.get("X_OAUTH_CLIENT_ID", ""),
            client_secret=os.environ.get("X_OAUTH_CLIENT_SECRET", ""),
            cost=cost,
        )
    except (OAuthError, Exception):
        client = None

    lines = [
        f"# Weekly review — {today.isoformat()}",
        "",
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
    ]
    lines += _format_mix_section()
    tail_lines = _eighty_hour_tail(client)
    lines += tail_lines
    lines += _decisions_block(events, tail_lines)

    if client:
        client.close()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"x-weekly-review-{today.isoformat()}.md"
    out.write_text("\n".join(lines))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
