#!/usr/bin/env python3
"""One-time OAuth 2.0 (PKCE) setup for the official X API.

Run: python scripts/auth.py
Opens your browser, captures the consent code on a loopback HTTP server,
exchanges it for tokens, and persists them to state/oauth_tokens.json (chmod 600).
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import os
import secrets
import socketserver
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.clients.official import TOKEN_URL, _basic_auth, save_tokens  # type: ignore  # noqa: E402

CALLBACK_HOST = "127.0.0.1"
CALLBACK_PORT = 8765
REDIRECT_URI = f"http://{CALLBACK_HOST}:{CALLBACK_PORT}/callback"
AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"
SCOPES = ["tweet.read", "tweet.write", "users.read", "offline.access"]
ENV_PATH = Path.home() / ".config" / "x-control" / ".env"

# Filled by the callback handler.
_received: dict[str, str] = {}
_done = threading.Event()


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        _received.update(dict(urllib.parse.parse_qsl(parsed.query)))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        ok = "code" in _received
        msg = "Auth captured. You can close this tab." if ok else f"Auth failed: {_received}"
        self.wfile.write(f"<html><body><h2>{msg}</h2></body></html>".encode())
        _done.set()

    def log_message(self, *_a, **_kw) -> None:  # silence noisy default logging
        return


def _serve_once() -> None:
    with socketserver.TCPServer((CALLBACK_HOST, CALLBACK_PORT), _CallbackHandler) as srv:
        srv.timeout = 1
        while not _done.is_set():
            srv.handle_request()


def main() -> int:
    load_dotenv(ENV_PATH)
    client_id = os.environ.get("X_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("X_OAUTH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        print(f"X_OAUTH_CLIENT_ID/SECRET missing in {ENV_PATH}")
        return 2

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    print("Opening browser for X OAuth consent…")
    print(f"  If it doesn't open, visit:\n  {url}\n")
    server_thread = threading.Thread(target=_serve_once, daemon=True)
    server_thread.start()
    time.sleep(0.2)
    webbrowser.open(url)

    if not _done.wait(timeout=300):
        print("Timed out waiting for callback (5 min). Aborting.")
        return 3
    server_thread.join(timeout=2)

    if _received.get("state") != state:
        print(f"State mismatch — possible CSRF. got={_received.get('state')!r}")
        return 4
    code = _received.get("code")
    if not code:
        print(f"No code in callback: {_received}")
        return 5

    print("Exchanging code for tokens…")
    r = httpx.post(
        TOKEN_URL,
        headers={
            "Authorization": _basic_auth(client_id, client_secret),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
            "client_id": client_id,
        },
        timeout=15,
    )
    if r.status_code != 200:
        print(f"Token exchange failed {r.status_code}: {r.text}")
        return 6
    body = r.json()
    tokens = {
        "access_token": body["access_token"],
        "refresh_token": body.get("refresh_token"),
        "expires_at": int(time.time()) + int(body.get("expires_in", 7200)),
        "scope": body.get("scope"),
    }
    if not tokens["refresh_token"]:
        print("WARNING: no refresh_token returned. Check that the `offline.access` scope is enabled on the app.")

    # Fetch identity so monitor.py doesn't need an extra call later.
    me = httpx.get(
        "https://api.x.com/2/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        timeout=15,
    )
    if me.status_code == 200:
        data = me.json().get("data", {})
        tokens["user_id"] = data.get("id")
        tokens["username"] = data.get("username")
        print(f"Authenticated as @{tokens['username']} ({tokens['user_id']})")
    else:
        print(f"WARNING: /2/users/me returned {me.status_code} — saving tokens anyway")

    save_tokens(tokens)
    print(f"Saved tokens to {ROOT / 'state' / 'oauth_tokens.json'} (mode 0600).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
