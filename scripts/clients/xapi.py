"""xapi.to client — KOL reads only. Never sees your X credentials.

Endpoint shape is unknown until first call. We probe a small set of common
patterns against the user's own handle, cache the working one, then reuse.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from ..cost import CostTracker

DEFAULT_BASE_URL = "https://api.xapi.to"
SHAPE_CACHE = Path(__file__).resolve().parents[2] / "state" / "xapi_endpoint_shape.json"

# Tried in order on first call. The placeholder {handle} is filled with the
# user's own handle; the first 2xx wins and is cached.
USER_BY_HANDLE_CANDIDATES = [
    "/v1/users/by/username/{handle}",       # X API v2-style
    "/v1/user/by/username/{handle}",
    "/v2/twitter/user/{handle}",
    "/twitter/user/info?screen_name={handle}",
    "/v1/user/{handle}",
    "/user/{handle}",
]

# Cost: ~$0.05 per 1k tweets cited in market comparison → $0.00005/tweet.
# Apply same per-call rate to user lookups as a rough upper bound.
COST_PER_TWEET = 0.00005
COST_PER_USER_LOOKUP = 0.00005


class XapiClient:
    def __init__(self, api_key: str, cost: CostTracker, base_url: str | None = None):
        if not api_key:
            raise ValueError("XAPI_API_KEY missing — fill ~/.config/x-control/.env")
        self.api_key = api_key
        self.cost = cost
        self.base_url = (base_url or os.environ.get("XAPI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.http = httpx.Client(
            timeout=httpx.Timeout(15.0, connect=5.0),
            headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
        )
        self._shape: dict[str, str] = self._load_shape()

    # ------------------------------------------------------------------ helpers
    def _load_shape(self) -> dict[str, str]:
        if SHAPE_CACHE.exists():
            try:
                return json.loads(SHAPE_CACHE.read_text())
            except json.JSONDecodeError:
                return {}
        return {}

    def _save_shape(self) -> None:
        SHAPE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        SHAPE_CACHE.write_text(json.dumps(self._shape, indent=2))

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        url = f"{self.base_url}{path}"
        backoff = 1.0
        for attempt in range(5):
            try:
                r = self.http.request(method, url, **kw)
            except httpx.HTTPError as e:
                if attempt == 4:
                    raise
                time.sleep(backoff)
                backoff *= 2
                continue
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 4:
                wait = float(r.headers.get("Retry-After", backoff))
                time.sleep(wait)
                backoff *= 2
                continue
            return r
        return r  # type: ignore[unreachable]

    # ------------------------------------------------------------------ probe
    def probe_user_endpoint(self, probe_handle: str) -> str:
        """Find the working user-by-handle path. Called once if cache empty."""
        cached = self._shape.get("user_by_handle")
        if cached:
            return cached
        h = probe_handle.lstrip("@")
        for candidate in USER_BY_HANDLE_CANDIDATES:
            path = candidate.format(handle=h)
            r = self._request("GET", path)
            if 200 <= r.status_code < 300 and r.headers.get("content-type", "").startswith("application/json"):
                self._shape["user_by_handle"] = candidate
                self._save_shape()
                return candidate
        raise RuntimeError(
            f"xapi.to probe failed against /{', '.join(c.split('?')[0] for c in USER_BY_HANDLE_CANDIDATES)}. "
            "Check the xapi.to docs for the correct user-by-username path and "
            "set it manually in state/xapi_endpoint_shape.json."
        )

    # ------------------------------------------------------------------ public API
    def user_by_handle(self, handle: str, probe_handle: str | None = None) -> dict[str, Any]:
        shape = self._shape.get("user_by_handle") or self.probe_user_endpoint(probe_handle or handle)
        path = shape.format(handle=handle.lstrip("@"))
        r = self._request("GET", path)
        r.raise_for_status()
        self.cost.charge(f"xapi.user_by_handle({handle})", COST_PER_USER_LOOKUP)
        return r.json()

    def user_tweets(self, user_id: str, max_results: int = 20) -> dict[str, Any]:
        # Try the v2-style path first; fall back through cache.
        for path in (
            f"/v1/users/{user_id}/tweets",
            f"/v1/user/{user_id}/tweets",
            f"/v2/twitter/user/{user_id}/tweets",
        ):
            r = self._request("GET", path, params={"max_results": max_results})
            if 200 <= r.status_code < 300:
                self.cost.charge(f"xapi.user_tweets({user_id})", COST_PER_TWEET * max_results)
                return r.json()
        r.raise_for_status()
        return {}

    def tweet_quotes(self, tweet_id: str, max_results: int = 20) -> dict[str, Any]:
        for path in (
            f"/v1/tweets/{tweet_id}/quotes",
            f"/v1/tweet/{tweet_id}/quotes",
        ):
            r = self._request("GET", path, params={"max_results": max_results})
            if 200 <= r.status_code < 300:
                self.cost.charge(f"xapi.tweet_quotes({tweet_id})", COST_PER_TWEET * max_results)
                return r.json()
        r.raise_for_status()
        return {}

    def close(self) -> None:
        self.http.close()
