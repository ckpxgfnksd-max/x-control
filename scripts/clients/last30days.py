"""KOL reads via the bundled bird-search.mjs from ~/.claude/skills/last30days/.

Replaces the failed xapi.to integration. Uses your existing cookies (AUTH_TOKEN /
CT0) from ~/.config/last30days/.env. Free — no per-call cost.

Caveats vs the original xapi.to plan:
- Bird is search-only. No follower_count is returned. Follower deltas drop;
  posting-velocity deltas (tweet_count_24h diff) replace them.
- No reliable quote-tweet search syntax found via Bird. Quote-tree hooks drop.
- Engagement metrics surfaced per tweet: likeCount, retweetCount, replyCount.
  No quote_count or impression_count (Bird strips those from search responses).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..cost import CostTracker

LAST30DAYS_ENV = Path.home() / ".config" / "last30days" / ".env"
BIRD_SEARCH = (
    Path.home()
    / ".claude" / "skills" / "last30days" / "scripts" / "lib" / "vendor"
    / "bird-search" / "bird-search.mjs"
)


class BirdNotConfigured(RuntimeError):
    pass


class Last30DaysClient:
    def __init__(self, cost: CostTracker, timeout: int = 60):
        if not BIRD_SEARCH.exists():
            raise BirdNotConfigured(
                f"bird-search.mjs not found at {BIRD_SEARCH}. "
                "Install or fix ~/.claude/skills/last30days/."
            )
        if not shutil.which("node"):
            raise BirdNotConfigured("`node` not in PATH — install Node.js 22+.")
        self.cost = cost
        self.timeout = timeout
        self.env = self._build_env()
        if not (self.env.get("AUTH_TOKEN") and self.env.get("CT0")):
            raise BirdNotConfigured(
                f"AUTH_TOKEN/CT0 missing from {LAST30DAYS_ENV}. "
                "Run /last30days setup or paste cookies into that .env."
            )

    # ------------------------------------------------------------------ env
    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if LAST30DAYS_ENV.exists():
            for raw in LAST30DAYS_ENV.read_text().splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                env[k.strip()] = v
        # Don't fall back to system browser cookies — automation should fail
        # loud if injected creds are missing rather than prompt for keychain.
        env["BIRD_DISABLE_BROWSER_COOKIES"] = "1"
        return env

    # ------------------------------------------------------------------ search
    def _search(self, query: str, count: int = 20) -> list[dict[str, Any]]:
        result = subprocess.run(
            ["node", str(BIRD_SEARCH), query, "--count", str(count), "--json"],
            capture_output=True,
            text=True,
            timeout=self.timeout,
            env=self.env,
        )
        if result.returncode not in (0, 1):
            raise RuntimeError(
                f"bird-search exit {result.returncode}: {result.stderr[:300]}"
            )
        out = (result.stdout or "").strip()
        if not out:
            return []
        try:
            data = json.loads(out)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"bird-search non-JSON output: {out[:300]} ({e})")
        if isinstance(data, dict):
            if data.get("error"):
                raise RuntimeError(f"bird-search: {data['error'][:300]}")
            data = data.get("items", [])
        if not isinstance(data, list):
            return []
        self.cost.charge(f"bird.search({query[:40]})", 0.0)
        return data

    # ------------------------------------------------------------------ public
    def user_recent_tweets(
        self, handle: str, count: int = 20, exclude_replies: bool = True
    ) -> dict[str, Any]:
        """Recent tweets for an @handle. Returns the normalized shape monitor.py
        expects. Author info pulled from the first tweet's `author` block —
        Bird does not provide follower_count.
        """
        h = handle.lstrip("@")
        # `-filter:replies` strips replies; keep originals + retweets.
        # Bird passes the query verbatim to X search.
        q = f"from:{h}" + (" -filter:replies" if exclude_replies else "")
        tweets = self._search(q, count=count)
        author: dict[str, Any] = {}
        if tweets:
            a = tweets[0].get("author") or {}
            author = {
                "id": tweets[0].get("authorId"),
                "username": a.get("username") or h,
                "name": a.get("name"),
                "followers_count": None,  # not available via Bird
            }
        else:
            author = {"id": None, "username": h, "name": None, "followers_count": None}
        return {"author": author, "tweets": tweets}

    def healthcheck(self) -> bool:
        """`--check` ping. True if cookies resolve."""
        try:
            r = subprocess.run(
                ["node", str(BIRD_SEARCH), "--check"],
                capture_output=True, text=True, timeout=15, env=self.env,
            )
            if r.returncode != 0:
                return False
            data = json.loads(r.stdout or "{}")
            return bool(data.get("authenticated"))
        except Exception:
            return False

    def close(self) -> None:
        return  # no persistent resources
