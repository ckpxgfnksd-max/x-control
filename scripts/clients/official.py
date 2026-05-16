"""Official X API v2 client with OAuth 2.0 (PKCE, confidential client).

Token storage: state/oauth_tokens.json (chmod 600). Refresh token rotates on
every use and is persisted back. On 401, the client refreshes once and retries.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

from ..cost import CostTracker

TOKEN_FILE = Path(__file__).resolve().parents[2] / "state" / "oauth_tokens.json"

API_BASE = "https://api.x.com"
TOKEN_URL = f"{API_BASE}/2/oauth2/token"

# Rate card per developer.x.com (April 2026 update)
COST_OWNED_READ = 0.001     # your own resources
COST_POST_READ = 0.005      # someone else's tweets
COST_USER_READ = 0.010      # user lookups, followers/following, etc.
COST_WRITE = 0.015          # POST /2/tweets (no URL)
COST_WRITE_URL = 0.200      # POST /2/tweets containing a URL
COST_DELETE = 0.010

URL_RE = re.compile(r"https?://\S+")


class OAuthError(RuntimeError):
    pass


def _basic_auth(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def load_tokens() -> dict[str, Any]:
    if not TOKEN_FILE.exists():
        raise OAuthError(
            f"no tokens at {TOKEN_FILE}. Run `python scripts/auth.py` first."
        )
    return json.loads(TOKEN_FILE.read_text())


def save_tokens(tokens: dict[str, Any]) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2))
    os.chmod(TOKEN_FILE, 0o600)


class OfficialXClient:
    def __init__(self, client_id: str, client_secret: str, cost: CostTracker):
        if not client_id or not client_secret:
            raise OAuthError("X_OAUTH_CLIENT_ID/SECRET missing in .env")
        self.client_id = client_id
        self.client_secret = client_secret
        self.cost = cost
        self.tokens = load_tokens()
        self._me_id: str | None = self.tokens.get("user_id")
        self.http = httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0))

    # ------------------------------------------------------------------ auth
    def _refresh(self) -> None:
        refresh = self.tokens.get("refresh_token")
        if not refresh:
            raise OAuthError("no refresh_token; re-run auth.py")
        r = self.http.post(
            TOKEN_URL,
            headers={
                "Authorization": _basic_auth(self.client_id, self.client_secret),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": self.client_id,
            },
        )
        if r.status_code != 200:
            raise OAuthError(f"refresh failed {r.status_code}: {r.text}")
        new = r.json()
        # Refresh rotates: preserve user_id, replace tokens + expiry.
        self.tokens.update({
            "access_token": new["access_token"],
            "refresh_token": new.get("refresh_token", refresh),
            "expires_at": int(time.time()) + int(new.get("expires_in", 7200)),
            "scope": new.get("scope", self.tokens.get("scope")),
        })
        save_tokens(self.tokens)

    def _bearer(self) -> str:
        if int(time.time()) >= int(self.tokens.get("expires_at", 0)) - 60:
            self._refresh()
        return f"Bearer {self.tokens['access_token']}"

    # ------------------------------------------------------------------ HTTP
    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        url = f"{API_BASE}{path}"
        headers = kw.pop("headers", {}) | {"Authorization": self._bearer()}
        backoff = 1.0
        refreshed = False
        for attempt in range(5):
            r = self.http.request(method, url, headers=headers, **kw)
            if r.status_code == 401 and not refreshed:
                # Force a refresh once and retry with new bearer.
                self._refresh()
                headers["Authorization"] = f"Bearer {self.tokens['access_token']}"
                refreshed = True
                continue
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 4:
                wait = float(r.headers.get("Retry-After", backoff))
                time.sleep(wait)
                backoff *= 2
                continue
            return r
        return r  # type: ignore[unreachable]

    # ------------------------------------------------------------------ identity
    def me(self) -> dict[str, Any]:
        if self._me_id:
            return {"id": self._me_id, "username": self.tokens.get("username")}
        r = self._request("GET", "/2/users/me")
        r.raise_for_status()
        self.cost.charge("official.me", COST_OWNED_READ)
        data = r.json()["data"]
        self._me_id = data["id"]
        self.tokens["user_id"] = data["id"]
        self.tokens["username"] = data.get("username")
        save_tokens(self.tokens)
        return data

    # ------------------------------------------------------------------ reads
    def me_tweets(self, max_results: int = 20) -> list[dict[str, Any]]:
        me = self.me()
        r = self._request(
            "GET",
            f"/2/users/{me['id']}/tweets",
            params={
                "max_results": max_results,
                "tweet.fields": "public_metrics,created_at,referenced_tweets",
                "exclude": "retweets",
            },
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        self.cost.charge("official.me_tweets", COST_OWNED_READ * max(1, len(data)))
        return data

    def me_mentions(self, max_results: int = 20) -> list[dict[str, Any]]:
        me = self.me()
        r = self._request(
            "GET",
            f"/2/users/{me['id']}/mentions",
            params={
                "max_results": max_results,
                "tweet.fields": "public_metrics,created_at,author_id",
                "expansions": "author_id",
                "user.fields": "username,public_metrics",
            },
        )
        r.raise_for_status()
        body = r.json()
        data = body.get("data", [])
        # Mentions are reads of others' tweets to you. Plan classifies as user-read
        # tier ($0.010) — they involve user lookups via expansions.
        self.cost.charge("official.me_mentions", COST_USER_READ * max(1, len(data)))
        return body  # caller wants includes too

    def tweet_metrics(self, tweet_id: str, is_owned: bool = False) -> dict[str, Any]:
        r = self._request(
            "GET",
            f"/2/tweets/{tweet_id}",
            params={"tweet.fields": "public_metrics,non_public_metrics,organic_metrics,created_at"},
        )
        r.raise_for_status()
        self.cost.charge(
            f"official.tweet_metrics({tweet_id})",
            COST_OWNED_READ if is_owned else COST_POST_READ,
        )
        return r.json().get("data", {})

    # ------------------------------------------------------------------ writes
    def post(self, text: str, in_reply_to: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"text": text}
        if in_reply_to:
            body["reply"] = {"in_reply_to_tweet_id": in_reply_to}
        r = self._request("POST", "/2/tweets", json=body)
        if r.status_code >= 300:
            raise RuntimeError(f"post failed {r.status_code}: {r.text}")
        has_url = bool(URL_RE.search(text))
        self.cost.charge(
            "official.post_with_url" if has_url else "official.post",
            COST_WRITE_URL if has_url else COST_WRITE,
        )
        return r.json().get("data", {})

    def delete(self, tweet_id: str) -> bool:
        r = self._request("DELETE", f"/2/tweets/{tweet_id}")
        if r.status_code >= 300:
            raise RuntimeError(f"delete failed {r.status_code}: {r.text}")
        self.cost.charge("official.delete", COST_DELETE)
        return r.json().get("data", {}).get("deleted", False)

    def close(self) -> None:
        self.http.close()
