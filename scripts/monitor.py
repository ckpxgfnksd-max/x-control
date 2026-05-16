#!/usr/bin/env python3
"""Daily X pulse runner. Writes ~/Documents/Last30Days/x-pulse-YYYY-MM-DD.md."""
from __future__ import annotations

import argparse
import os
import re
import sys
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # so `from scripts import ...` works when run as a file

from scripts import state                                      # noqa: E402
from scripts.cost import CostCapExceeded, CostTracker          # noqa: E402
from scripts.clients.last30days import (                       # noqa: E402
    Last30DaysClient,
    BirdNotConfigured,
)
from scripts.clients.official import OfficialXClient, OAuthError  # noqa: E402
from scripts.digest import render                              # noqa: E402

ENV_PATH = Path.home() / ".config" / "x-control" / ".env"
KOL_LIST_PATH = ROOT / "kol_list.md"
KOL_LIST_EXAMPLE = ROOT / "kol_list.example.md"
PULSE_DIR = Path.home() / "Documents" / "Last30Days"

VIRAL_LIKES = 500            # threshold for a KOL post to be flagged viral
VIRAL_REPLIES = 100          # alt threshold: high reply chatter
VIRAL_WINDOW_HOURS = 24      # measured from tweet's created_at
VELOCITY_FLAG_RATIO = 1.5    # tweet_count today / prior ≥ 1.5x → "posting surge"
VELOCITY_FLAG_MIN_DELTA = 3  # require an absolute increase of N tweets too


# -----------------------------------------------------------------------------
# kol list parsing
# -----------------------------------------------------------------------------
@dataclass
class KolRow:
    handle: str
    category: str
    weight: float
    note: str = ""

    @property
    def is_own(self) -> bool:
        return self.category.lower() == "own"


def parse_kol_list(path: Path) -> list[KolRow]:
    rows: list[KolRow] = []
    in_table = False
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            in_table = False
            continue
        if set(line.replace("|", "").strip()) <= set("-: "):
            in_table = True
            continue
        if not in_table:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not cells[0] or cells[0].lower() == "handle":
            continue
        try:
            weight = float(cells[2])
        except ValueError:
            weight = 1.0
        rows.append(KolRow(
            handle=cells[0].lstrip("@"),
            category=cells[1],
            weight=weight,
            note=cells[3] if len(cells) > 3 else "",
        ))
    return rows


# -----------------------------------------------------------------------------
# pulse data model
# -----------------------------------------------------------------------------
@dataclass
class PulseData:
    today: date
    own_handle: str = ""
    own_tweets: list[dict[str, Any]] = field(default_factory=list)
    own_mentions: dict[str, Any] = field(default_factory=dict)
    kol_rows: list[dict[str, Any]] = field(default_factory=list)
    viral_posts: list[dict[str, Any]] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    cost_summary: str = ""
    notes: list[str] = field(default_factory=list)


# -----------------------------------------------------------------------------
# helpers
# -----------------------------------------------------------------------------
def _parse_ts(ts: str | None) -> datetime | None:
    """Parse timestamps from both official X API (ISO 8601) and Bird search
    (Twitter's RFC 822-style: 'Thu May 14 19:55:03 +0000 2026')."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return datetime.strptime(ts, "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        return None


def _hours_since(ts: str | None) -> float:
    dt = _parse_ts(ts)
    if not dt:
        return 1e9
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0


def _normalize_user_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """xapi.to shape unknown — pluck common fields from a few plausible layouts."""
    inner = raw.get("data") or raw.get("user") or raw
    metrics = inner.get("public_metrics") or inner.get("metrics") or {}
    return {
        "id": inner.get("id") or inner.get("user_id") or inner.get("rest_id"),
        "username": inner.get("username") or inner.get("screen_name") or inner.get("handle"),
        "follower_count": (
            inner.get("followers_count")
            or inner.get("follower_count")
            or metrics.get("followers_count")
        ),
        "name": inner.get("name"),
    }


def _normalize_tweet_payload(t: dict[str, Any]) -> dict[str, Any]:
    """Normalize tweet shape across official X API v2 + Bird search output.

    Official: public_metrics nested. Bird: likeCount/retweetCount/replyCount flat,
    createdAt camelCase. No quote_count or impression_count in Bird output.
    """
    metrics = t.get("public_metrics") or {}
    return {
        "id": t.get("id") or t.get("id_str") or t.get("rest_id"),
        "text": t.get("text") or t.get("full_text") or t.get("content") or "",
        "created_at": t.get("created_at") or t.get("createdAt"),
        "like_count": (
            metrics.get("like_count")
            or t.get("likeCount")
            or t.get("favorite_count")
            or 0
        ),
        "retweet_count": (
            metrics.get("retweet_count")
            or t.get("retweetCount")
            or t.get("retweet_count")
            or 0
        ),
        "reply_count": (
            metrics.get("reply_count")
            or t.get("replyCount")
            or t.get("reply_count")
            or 0
        ),
        "quote_count": metrics.get("quote_count") or t.get("quoteCount") or 0,
        "impression_count": metrics.get("impression_count") or 0,
    }


# -----------------------------------------------------------------------------
# blocks
# -----------------------------------------------------------------------------
def fetch_own_block(client: OfficialXClient, data: PulseData) -> None:
    me = client.me()
    data.own_handle = me.get("username", "")
    tweets = client.me_tweets(max_results=20)
    data.own_tweets = [
        {**_normalize_tweet_payload(t), "owned": True}
        for t in tweets
        if _hours_since(t.get("created_at")) <= 24
    ]
    data.own_mentions = client.me_mentions(max_results=20)


def fetch_kol_block(
    client: Last30DaysClient,
    kols: list[KolRow],
    data: PulseData,
    prev_snapshot: dict[str, Any] | None,
    today_snapshot: dict[str, Any],
    only: str | None,
) -> None:
    """Fetch KOL recent activity via Bird (cookies). Surfaces:
    - posting velocity delta (tweet_count_24h diff vs prior snapshot)
    - viral KOL posts (likes ≥ VIRAL_LIKES OR replies ≥ VIRAL_REPLIES in last 24h)

    No follower counts (Bird doesn't surface them), no quote-tree hooks (no
    reliable quote-search syntax). The trade vs the original xapi.to plan: free
    + always available, at the cost of those two signals.
    """
    for k in kols:
        if k.is_own:
            continue
        if only and k.handle.lower() != only.lstrip("@").lower():
            continue
        try:
            payload = client.user_recent_tweets(k.handle, count=20)
            tweets = [_normalize_tweet_payload(t) for t in payload.get("tweets", [])]
            recent = [t for t in tweets if _hours_since(t.get("created_at")) <= 24]

            today_snapshot[k.handle] = {
                "tweet_ids": [t["id"] for t in tweets if t.get("id")][:20],
                "tweet_count_24h": len(recent),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }

            prev = (prev_snapshot or {}).get(k.handle, {})
            prev_count = prev.get("tweet_count_24h")
            now_count = len(recent)
            velocity_delta = None
            velocity_ratio = None
            flagged = False
            if isinstance(prev_count, (int, float)) and prev_count > 0:
                velocity_delta = now_count - prev_count
                velocity_ratio = now_count / prev_count
                flagged = (
                    velocity_ratio >= VELOCITY_FLAG_RATIO
                    and velocity_delta >= VELOCITY_FLAG_MIN_DELTA
                )

            data.kol_rows.append({
                "handle": k.handle,
                "category": k.category,
                "weight": k.weight,
                "tweet_count_24h": now_count,
                "prev_count": prev_count,
                "velocity_delta": velocity_delta,
                "velocity_ratio": velocity_ratio,
                "flagged": flagged,
            })

            for t in recent:
                if _hours_since(t.get("created_at")) > VIRAL_WINDOW_HOURS:
                    continue
                if (
                    (t["like_count"] or 0) < VIRAL_LIKES
                    and (t["reply_count"] or 0) < VIRAL_REPLIES
                ):
                    continue
                data.viral_posts.append({
                    "handle": k.handle,
                    "tweet": t,
                    "url": f"https://x.com/{k.handle}/status/{t['id']}",
                    "quote_hooks": [],  # Bird has no quote-search syntax
                })
        except CostCapExceeded:
            raise
        except Exception as e:
            data.failures.append(f"@{k.handle}: {e}")


# -----------------------------------------------------------------------------
# main
# -----------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Daily X pulse")
    ap.add_argument("--dry-run", action="store_true", help="print plan, no network")
    ap.add_argument("--skip-kols", action="store_true", help="own-account section only")
    ap.add_argument("--only", help="limit KOL fan-out to this handle")
    args = ap.parse_args()

    load_dotenv(ENV_PATH)
    today = date.today()

    # Fall back to the shipped template if user hasn't created their own yet.
    if KOL_LIST_PATH.exists():
        kol_path = KOL_LIST_PATH
    elif KOL_LIST_EXAMPLE.exists():
        kol_path = KOL_LIST_EXAMPLE
        print(f"⚠  using {KOL_LIST_EXAMPLE.name} — copy to kol_list.md and edit your KOLs")
    else:
        print(f"✗ no kol list found (looked for {KOL_LIST_PATH} or {KOL_LIST_EXAMPLE})")
        return 2
    kols = parse_kol_list(kol_path)
    own = next((k for k in kols if k.is_own), None)
    if own and own.handle.upper() == "YOUR_HANDLE":
        print("✗ kol_list.md still has the placeholder 'YOUR_HANDLE'. "
              "Edit it to your X handle before running.")
        return 2

    if args.dry_run:
        from scripts.clients.last30days import LAST30DAYS_ENV
        print(f"== dry-run for {today} ==")
        print(f"own handle:    @{own.handle if own else '<unset>'}")
        print(f"kol count:     {sum(1 for k in kols if not k.is_own)}")
        print(f"pulse target:  {PULSE_DIR / f'x-pulse-{today.isoformat()}.md'}")
        print(f"env file:      {ENV_PATH} (exists={ENV_PATH.exists()})")
        print(f"oauth set:     {bool(os.environ.get('X_OAUTH_CLIENT_ID'))}")
        print(f"last30days env: {LAST30DAYS_ENV} (exists={LAST30DAYS_ENV.exists()})")
        print(f"cap usd:       {os.environ.get('MAX_DAILY_API_SPEND_USD', '2.00')}")
        return 0

    cost = CostTracker()
    data = PulseData(today=today, own_handle=own.handle if own else "")

    # --- own block ---
    official: OfficialXClient | None = None
    try:
        official = OfficialXClient(
            client_id=os.environ.get("X_OAUTH_CLIENT_ID", ""),
            client_secret=os.environ.get("X_OAUTH_CLIENT_SECRET", ""),
            cost=cost,
        )
        fetch_own_block(official, data)
    except OAuthError as e:
        data.failures.append(f"official OAuth: {e}")
    except CostCapExceeded as e:
        data.failures.append(f"cost cap during own block: {e}")
    except Exception as e:
        data.failures.append(f"own block: {e}\n{traceback.format_exc(limit=1)}")
    finally:
        if official:
            official.close()

    # --- kol block ---
    today_snapshot: dict[str, Any] = {}
    prev_loaded = state.load_previous(today)
    prev_snapshot = prev_loaded[1] if prev_loaded else None
    if prev_loaded:
        data.notes.append(f"deltas vs snapshot from {prev_loaded[0].isoformat()}")
    else:
        data.notes.append("no prior snapshot — deltas available from tomorrow")

    if not args.skip_kols:
        try:
            l30 = Last30DaysClient(cost=cost)
        except BirdNotConfigured as e:
            data.failures.append(f"last30days: {e}")
        else:
            try:
                fetch_kol_block(
                    l30, kols, data, prev_snapshot, today_snapshot, args.only
                )
            except CostCapExceeded as e:
                data.failures.append(f"cost cap during KOL block: {e}")
            except Exception as e:
                data.failures.append(f"KOL block: {e}\n{traceback.format_exc(limit=1)}")
            finally:
                l30.close()

    # Persist snapshot (only if we got any KOLs; never overwrite with empty).
    if today_snapshot:
        state.save(today_snapshot, today)

    data.cost_summary = cost.summary()

    # --- optional data dump for autoresearch (set X_CONTROL_DUMP_DATA=1) ---
    if os.environ.get("X_CONTROL_DUMP_DATA"):
        from dataclasses import asdict
        import json as _json
        dump_path = PULSE_DIR / f"_pulse_data_{today.isoformat()}.json"
        dump_path.write_text(_json.dumps(asdict(data), indent=2, default=str))

    # --- render ---
    PULSE_DIR.mkdir(parents=True, exist_ok=True)
    out = PULSE_DIR / f"x-pulse-{today.isoformat()}.md"
    out.write_text(render(data))

    # Also render the HTML dashboard (cbti-style) alongside the markdown.
    try:
        from bench.render_dashboard import render_html
        from dataclasses import asdict
        html_out = PULSE_DIR / f"x-pulse-{today.isoformat()}.html"
        html_out.write_text(render_html(asdict(data)))
    except Exception as _e:
        pass  # dashboard is optional; never block the pulse on it
    print(f"wrote {out}")
    print(cost.summary())
    if data.failures:
        print(f"{len(data.failures)} warnings (see digest footer)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
