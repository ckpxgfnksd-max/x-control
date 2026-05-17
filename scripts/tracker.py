"""Weekly ship-event tracker — records every approved post so the digest can
flag format/language gaps and the weekly review can roll up trends.

State at ~/.claude/skills/x-control/state/weekly_tracker.json:
{
  "events": [
    {"ts": "2026-05-16T17:23:11+00:00",
     "tweet_id": "...",
     "format": "standalone|thread|reply|video|longform",
     "lang": "cn|en|mixed",
     "is_reply": false,
     "tweet_count": 1,          # how many tweets in this ship (1 for standalone, N for thread)
     "char_count": 247,
     # Optional authoring metadata (added 2026-05-17, all default to empty/None
     # so old state files load without migration):
     "topic_tags": ["tokenomics"],
     "angle_type": "contrarian",
     "audience_pool": "in_network",
     "format_goal": "profile_clicks",
     "experiment_label": "cn-thread-v2"}
  ]
}
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1] / "state"
TRACKER_FILE = ROOT / "weekly_tracker.json"

URL_RE = re.compile(r"https?://|t\.co/")


def _load() -> dict[str, Any]:
    if not TRACKER_FILE.exists():
        return {"events": []}
    try:
        return json.loads(TRACKER_FILE.read_text())
    except json.JSONDecodeError:
        return {"events": []}


def _save(data: dict[str, Any]) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    TRACKER_FILE.write_text(json.dumps(data, indent=2))


def _detect_lang(text: str) -> str:
    cn = bool(re.search(r"[一-鿿]", text))
    en = bool(re.search(r"[A-Za-z]{8,}", text))
    if cn and en:
        return "mixed"
    return "cn" if cn else "en"


def _detect_format(tweets: list[str], is_reply: bool) -> str:
    if is_reply:
        return "reply"
    if len(tweets) > 1:
        return "thread"
    total_chars = sum(len(t) for t in tweets)
    if total_chars > 1000:
        return "longform"
    return "standalone"


# Authoring-metadata fields. Centralized so callers can iterate them and
# load() can fill missing defaults on legacy state files.
_AUTHORING_DEFAULTS: dict[str, Any] = {
    "topic_tags": [],
    "angle_type": None,
    "audience_pool": None,
    "format_goal": None,
    "experiment_label": None,
}


def _fill_defaults(event: dict[str, Any]) -> dict[str, Any]:
    """Ensure an event has the authoring-metadata fields with safe defaults.
    Mutates in place and returns the event for chaining."""
    for k, v in _AUTHORING_DEFAULTS.items():
        if k not in event:
            event[k] = list(v) if isinstance(v, list) else v
    return event


def record_ship(
    tweet_id: str,
    tweets: list[str],
    is_reply: bool,
    *,
    topic_tags: list[str] | None = None,
    angle_type: str | None = None,
    audience_pool: str | None = None,
    format_goal: str | None = None,
    experiment_label: str | None = None,
) -> dict[str, Any]:
    """Called from approve.py after a successful post. Returns the event dict.

    The authoring-metadata kwargs are pulled from draft frontmatter by the
    caller; all default to empty so old call sites stay compatible."""
    full_text = "\n\n".join(tweets)
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tweet_id": tweet_id,
        "format": _detect_format(tweets, is_reply),
        "lang": _detect_lang(full_text),
        "is_reply": is_reply,
        "tweet_count": len(tweets),
        "char_count": len(full_text),
        "topic_tags": list(topic_tags or []),
        "angle_type": angle_type,
        "audience_pool": audience_pool,
        "format_goal": format_goal,
        "experiment_label": experiment_label,
    }
    data = _load()
    data["events"].append(event)
    # Prune events older than 60 days to keep file bounded
    cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    data["events"] = [e for e in data["events"] if e["ts"] >= cutoff]
    _save(data)
    return event


def events_in_last(hours: float) -> list[dict[str, Any]]:
    """Events within the last N hours. Old events missing the authoring-metadata
    fields are upgraded with defaults so consumers can read uniformly."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    data = _load()
    return [_fill_defaults(dict(e)) for e in data["events"] if e["ts"] >= cutoff]


def topic_mix(hours: float = 24 * 30) -> dict[str, int]:
    """Return {topic: count} aggregated from event topic_tags over the window.
    Used by signals.topic_fit() and diagnose.py to know the account's recent mix."""
    from collections import Counter
    c: Counter = Counter()
    for e in events_in_last(hours):
        for t in e.get("topic_tags") or []:
            tag = str(t).strip().lower()
            if tag:
                c[tag] += 1
    return dict(c)


def angle_mix(hours: float = 24 * 14) -> dict[str, int]:
    """Return {angle: count} over the window. Powers S19 monoculture detection."""
    from collections import Counter
    c: Counter = Counter()
    for e in events_in_last(hours):
        a = e.get("angle_type")
        if a:
            c[str(a).strip().lower()] += 1
    return dict(c)


def experiment_mix(hours: float = 24 * 30) -> dict[str, list[dict[str, Any]]]:
    """Return {experiment_label: [events...]} for active experiments."""
    out: dict[str, list[dict[str, Any]]] = {}
    for e in events_in_last(hours):
        label = e.get("experiment_label")
        if label:
            out.setdefault(str(label).strip(), []).append(e)
    return out


def count_by_format(hours: float) -> dict[str, int]:
    from collections import Counter
    c = Counter(e["format"] for e in events_in_last(hours))
    return dict(c)


def standalone_count_24h() -> int:
    """Number of standalone (non-reply, non-thread, non-longform) posts in last 24h.
    This is the count that AuthorDiversityDecay penalizes."""
    return sum(
        1 for e in events_in_last(24)
        if e["format"] == "standalone"
    )


def reply_count_24h() -> int:
    return sum(1 for e in events_in_last(24) if e["format"] == "reply")
