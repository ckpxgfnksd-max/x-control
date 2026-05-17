"""Post queue — markdown files with YAML frontmatter in queue/{pending,posted,rejected}/."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1] / "queue"
PENDING = ROOT / "pending"
POSTED = ROOT / "posted"
REJECTED = ROOT / "rejected"

URL_RE = re.compile(r"https?://\S+")
EM_DASH_RE = re.compile(r"—")
EMOJI_HEAVY_RE = re.compile(
    "["
    "\U0001F300-\U0001F6FF"  # symbols & pictographs
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001F1E0-\U0001F1FF"  # flags
    "☀-➿"          # misc symbols
    "]"
)
RISK_PATTERNS: dict[str, re.Pattern] = {
    # Crypto-specific risks
    "price_target": re.compile(r"\$\d[\d,]*\s*(price|target|by\s+(eoy|end))", re.I),
    "guarantee_lang": re.compile(r"\b(guaranteed|100%|definitely|will hit)\b", re.I),
    "shill_keywords": re.compile(r"\b(100x|1000x|moonshot|to the moon|degen play|presale)\b", re.I),
    "dm_solicitation": re.compile(r"\bdm me\b|\bdms? are open\b", re.I),
    # Algorithm-aware risks (xai-org/x-algorithm: negative-feedback signals
    # carry explicit suppression weight — mute/block/report/"not interested")
    "callout_named_account": re.compile(
        r"@\w+\s+(is|was|are|were|just|literally)\s+"
        r"(wrong|stupid|lying|grifting|cooked|done|over|finished|delusional)\b",
        re.I,
    ),
    "engagement_bait": re.compile(
        r"\b(rt if|like if|retweet if)\b"
        r"|\bcomment\s+(yes|below|if|with)\b"
        r"|\b(do you agree|am i wrong|fight me|prove me wrong)\b\??\s*$"
        r"|\bwho else\b.*\?\s*$",
        re.I,
    ),
    "ai_slop_openers": re.compile(
        r"^\s*(let me explain|here's the thing|here's what|in this thread|"
        r"buckle up|grab a coffee|the truth is|nobody talks about|the dirty secret)",
        re.I,
    ),
}


def _has_em_dash_overuse(text: str, threshold: int = 3) -> bool:
    """3+ em-dashes in one tweet — common AI-generation tell."""
    return len(EM_DASH_RE.findall(text)) >= threshold


def _has_emoji_spam(text: str, threshold: int = 5) -> bool:
    return len(EMOJI_HEAVY_RE.findall(text)) >= threshold


def _is_numbered_list_tweet(text: str) -> bool:
    """Inline '1. X 2. Y 3. Z' pattern in a single tweet — reads as bullet slop."""
    return bool(re.search(r"\b1[\.)]\s.+\b2[\.)]\s.+\b3[\.)]\s", text))

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


@dataclass
class Draft:
    path: Path
    frontmatter: dict[str, Any]
    body: str

    @property
    def text(self) -> str:
        return self.body.strip()

    @property
    def tweets(self) -> list[str]:
        """Body split into one tweet per blank-line-separated block."""
        chunks = [c.strip() for c in re.split(r"\n\s*\n", self.body.strip()) if c.strip()]
        return chunks or [self.body.strip()]

    @property
    def kind(self) -> str:
        return str(self.frontmatter.get("type", "post"))

    @property
    def in_reply_to(self) -> str | None:
        v = self.frontmatter.get("parent_tweet_id")
        return str(v) if v else None

    # ── algorithm-aware authoring metadata (all optional) ───────────────────
    # These fields let signals.py and tracker.py reason about *what* the draft
    # is trying to do (positive-signal targeting), not just *what risks it
    # carries* (negative-feedback avoidance). All default to empty/None so
    # existing drafts continue to load unchanged.
    @property
    def topic_tags(self) -> list[str]:
        v = self.frontmatter.get("topic_tags") or []
        if isinstance(v, str):
            return [v]
        return [str(t).strip() for t in v if str(t).strip()]

    @property
    def angle_type(self) -> str | None:
        v = self.frontmatter.get("angle_type")
        return str(v).strip() if v else None

    @property
    def audience_pool(self) -> str | None:
        v = self.frontmatter.get("audience_pool")
        return str(v).strip() if v else None

    @property
    def format_goal(self) -> str | None:
        v = self.frontmatter.get("format_goal")
        return str(v).strip() if v else None

    @property
    def experiment_label(self) -> str | None:
        v = self.frontmatter.get("experiment_label")
        return str(v).strip() if v else None

    @property
    def identity_hints(self) -> list[str]:
        v = self.frontmatter.get("identity_hints") or []
        if isinstance(v, str):
            return [v]
        return [str(t).strip() for t in v if str(t).strip()]

    def risk_markers(self) -> list[str]:
        markers = []
        full = self.body
        for name, pat in RISK_PATTERNS.items():
            if pat.search(full):
                markers.append(name)
        # Per-tweet structural slop checks (run against each tweet in a thread)
        for chunk in self.tweets:
            if _has_em_dash_overuse(chunk):
                markers.append("em_dash_overuse")
                break
        for chunk in self.tweets:
            if _has_emoji_spam(chunk):
                markers.append("emoji_spam")
                break
        for chunk in self.tweets:
            if _is_numbered_list_tweet(chunk):
                markers.append("numbered_list_in_one_tweet")
                break
        if URL_RE.search(full):
            markers.append("contains_url_$0.20_per_post")
        return markers


def _parse(text: str) -> tuple[dict[str, Any], str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_raw, body = m.group(1), m.group(2)
    try:
        fm = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError:
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, body


def load(path: Path) -> Draft:
    fm, body = _parse(path.read_text())
    return Draft(path=path, frontmatter=fm, body=body)


def list_pending() -> list[Draft]:
    PENDING.mkdir(parents=True, exist_ok=True)
    drafts = [load(p) for p in sorted(PENDING.glob("*.md")) if p.is_file()]
    # Sort by target_time then created
    def key(d: Draft) -> str:
        return str(d.frontmatter.get("target_time") or d.frontmatter.get("created") or d.path.name)
    drafts.sort(key=key)
    return drafts


def write(draft: Draft) -> None:
    text = "---\n" + yaml.safe_dump(draft.frontmatter, sort_keys=False).rstrip() + "\n---\n" + draft.body
    draft.path.write_text(text)


def archive(draft: Draft, to: str, extra_frontmatter: dict[str, Any] | None = None) -> Path:
    dest_dir = {"posted": POSTED, "rejected": REJECTED}[to]
    dest_dir.mkdir(parents=True, exist_ok=True)
    if extra_frontmatter:
        draft.frontmatter.update(extra_frontmatter)
    draft.frontmatter["archived_at"] = datetime.now(timezone.utc).isoformat()
    dest = dest_dir / draft.path.name
    write(draft)  # update frontmatter in pending first
    draft.path.rename(dest)
    return dest


def posted_in_last(hours: float) -> int:
    """Count posts archived to queue/posted/ within the last N hours.

    Powers the burst warning: xai-org/x-algorithm's AuthorDiversityDecay
    exponentially penalizes the same author shown repeatedly to the same viewer,
    so 3+ standalone posts in a 4h window suppresses itself.
    """
    if not POSTED.exists():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    count = 0
    for p in POSTED.glob("*.md"):
        try:
            d = load(p)
        except Exception:
            continue
        ts = d.frontmatter.get("archived_at") or d.frontmatter.get("created")
        if not ts:
            continue
        try:
            when = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            continue
        if when >= cutoff:
            count += 1
    return count


def create_pending(
    text: str,
    *,
    type: str = "post",
    target_time: str | None = None,
    parent_tweet_id: str | None = None,
    slug: str | None = None,
) -> Path:
    PENDING.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    if not slug:
        snippet = re.sub(r"[^a-z0-9]+", "-", text.lower())[:40].strip("-") or "draft"
        slug = snippet
    name = f"{now.strftime('%Y%m%dT%H%M%S')}_{slug}.md"
    fm = {
        "created": now.isoformat(),
        "target_time": target_time,
        "type": type,
        "parent_tweet_id": parent_tweet_id,
        "character_count": len(text),
        "url_count": len(URL_RE.findall(text)),
    }
    path = PENDING / name
    body = text if not text.endswith("\n") else text
    out = "---\n" + yaml.safe_dump(fm, sort_keys=False).rstrip() + "\n---\n" + body + "\n"
    path.write_text(out)
    return path
