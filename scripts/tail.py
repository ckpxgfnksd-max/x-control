"""24-80h tail logic — shared between daily pulse and Sunday weekly review.

Tweets in the 24-80h window are still in Phoenix's candidate pool per
`POST_AGE_MAX_MINUTES = 4800` (`phoenix/recsys_model.py:30` in xai-org/x-algorithm).
The model's post-age embedding has 80 normal buckets + an overflow bucket;
past 80h, the model loses the ability to distinguish age and the post
collapses into the overflow bucket.

This module provides:
  - `fetch_tail(client)` — pull own tweets in the 24-80h window from the
    official API. Returns a list of normalized dicts with age_h precomputed.
  - `categorize(item, prior, median_imps)` — classify a tail item as
    'growing' / 'needs-rework' / 'dead' based on engagement_rate + impressions
    relative to the account's 30d median.
  - `from_pulse_data(data)` — read a precomputed tail array from a pulse_data
    dict (used by bench/fixtures so renderers don't need a live client).

Cost: one owned-read per fetch (~$0.001) plus the candidate list. With ~5
tweets typically in the window, this is ~$0.005/day = $0.15/month.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Public source citation — surface in renderings.
POST_AGE_MAX_MINUTES = 4800  # phoenix/recsys_model.py:30
POST_AGE_MAX_HOURS = POST_AGE_MAX_MINUTES // 60  # = 80
HOURS_MIN = 24
HOURS_MAX = 80

ROOT = Path(__file__).resolve().parents[1] / "state"


def _snapshot_path(d: date) -> Path:
    return ROOT / f"own_snapshot_{d.isoformat()}.json"


def save_own_snapshot(items: list[dict], on: date | None = None) -> Path | None:
    """Persist today's own-tweet metrics for tomorrow's delta comparison.
    Returns None if items is empty (don't overwrite a real snapshot with empty)."""
    if not items:
        return None
    on = on or date.today()
    ROOT.mkdir(parents=True, exist_ok=True)
    p = _snapshot_path(on)
    # Store only the fields we need to compute deltas tomorrow.
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "items": {
            it["id"]: {
                "impression_count": it.get("impression_count", 0),
                "like_count": it.get("like_count", 0),
                "retweet_count": it.get("retweet_count", 0),
                "reply_count": it.get("reply_count", 0),
            }
            for it in items
            if it.get("id")
        },
    }
    p.write_text(json.dumps(payload, indent=2))
    return p


def load_prior_own_snapshot(today: date | None = None, max_lookback: int = 7) -> dict[str, Any] | None:
    """Most recent own-tweet snapshot strictly before `today` (looks back up to
    max_lookback days). Returns the inner `items` dict or None."""
    today = today or date.today()
    for delta in range(1, max_lookback + 1):
        p = _snapshot_path(today - timedelta(days=delta))
        if p.exists():
            try:
                return json.loads(p.read_text()).get("items") or {}
            except json.JSONDecodeError:
                continue
    return None


def fetch_tail(client) -> list[dict]:
    """Fetch own tweets aged 24-80h via official API owned-reads.
    Returns a list of dicts with id/text/created_at/age_h/public_metrics fields.

    Raises any exception from the client — caller decides whether to swallow.
    """
    me = client.me()
    resp = client._request(
        "GET",
        f"/2/users/{me['id']}/tweets",
        params={
            "max_results": 100,
            "tweet.fields": "public_metrics,created_at",
            "exclude": "retweets",
        },
    )
    resp.raise_for_status()
    raw = resp.json().get("data", []) or []
    now = datetime.now(timezone.utc)
    out: list[dict] = []
    for t in raw:
        ts = t.get("created_at")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        age_h = (now - dt).total_seconds() / 3600.0
        if not (HOURS_MIN < age_h <= HOURS_MAX):
            continue
        m = t.get("public_metrics") or {}
        out.append({
            "id": t.get("id"),
            "text": t.get("text", ""),
            "created_at": ts,
            "age_h": age_h,
            "impression_count": m.get("impression_count", 0) or 0,
            "like_count": m.get("like_count", 0) or 0,
            "retweet_count": m.get("retweet_count", 0) or 0,
            "reply_count": m.get("reply_count", 0) or 0,
            "owner_handle": me.get("username") or "",
        })
    out.sort(key=lambda t: t["impression_count"], reverse=True)
    return out


def _engagement_rate(item: dict) -> float:
    imps = item.get("impression_count", 0) or 0
    if imps <= 0:
        return 0.0
    eng = (item.get("like_count", 0) or 0) + (item.get("retweet_count", 0) or 0) + (item.get("reply_count", 0) or 0)
    return eng / imps  # fraction, e.g. 0.015 = 1.5%


def categorize(item: dict, prior_item: dict | None, median_imps: float) -> str:
    """Classify a tail item.

    growing       — still gaining: ≥20% impression delta vs prior snapshot,
                    OR ≥1.5% engagement_rate AND age ≤ 60h.
    needs-rework  — high reach, weak hook: imps ≥ 2× median AND engagement_rate < 0.5%.
    dead          — low reach, late: imps < 0.5× median AND age ≥ 60h.

    Median acts as the per-account baseline so the same rules work across
    cold-start and big-account profiles. If median is 0 (no history), fall
    back to absolute thresholds (≥3000 imps = high, <500 = low).
    """
    imps = item.get("impression_count", 0) or 0
    age = item.get("age_h", 0.0)
    rate = _engagement_rate(item)

    high_thresh = 2 * median_imps if median_imps > 0 else 3000
    low_thresh = 0.5 * median_imps if median_imps > 0 else 500

    if prior_item:
        prior_imps = prior_item.get("impression_count", 0) or 0
        if imps > prior_imps and (imps - prior_imps) >= 0.2 * max(imps, 1):
            return "growing"
    if rate >= 0.015 and age <= 60:
        return "growing"
    if imps >= high_thresh and rate < 0.005:
        return "needs-rework"
    if imps < low_thresh and age >= 60:
        return "dead"
    return "stable"


def categorize_all(items: list[dict], prior: dict[str, Any] | None, median_imps: float) -> list[dict]:
    """Annotate each item with `category` and return the list."""
    prior_map = prior or {}
    out: list[dict] = []
    for it in items:
        cat = categorize(it, prior_map.get(it.get("id")), median_imps)
        out.append({**it, "category": cat})
    return out


def median_impressions(items: list[dict]) -> float:
    """Median impressions across the items (used as baseline). 0 if empty."""
    imps = sorted(int(i.get("impression_count", 0) or 0) for i in items)
    n = len(imps)
    if n == 0:
        return 0.0
    if n % 2 == 1:
        return float(imps[n // 2])
    return (imps[n // 2 - 1] + imps[n // 2]) / 2.0


def from_pulse_data(data: dict) -> list[dict]:
    """Read a precomputed `tail` array from a pulse_data dict (used by fixtures
    and renderers). Returns [] if absent. Items should already have `category`."""
    raw = data.get("tail") if isinstance(data, dict) else None
    return list(raw) if isinstance(raw, list) else []
