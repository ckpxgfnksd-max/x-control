#!/usr/bin/env python3
"""Interactive credential setup for ~/.config/x-control/.env.

No editor, no shell history, hidden input. Press Enter to skip a field and
keep whatever value is currently in the file (useful for partial updates).
"""
from __future__ import annotations

import getpass
import os
import sys
import tempfile
from pathlib import Path

ENV = Path.home() / ".config" / "x-control" / ".env"
ENV.parent.mkdir(parents=True, exist_ok=True)
os.chmod(ENV.parent, 0o700)

FIELDS = [
    # XAPI_API_KEY: legacy no-op slot, kept so older .env files don't error on
    # load. KOL reads use bird-search via /last30days cookies. Leave blank.
    ("XAPI_API_KEY",          "XAPI_API_KEY (legacy, leave blank)"),
    ("X_OAUTH_CLIENT_ID",     "X OAuth 2.0 Client ID"),
    ("X_OAUTH_CLIENT_SECRET", "X OAuth 2.0 Client Secret"),
]
DEFAULTS = {"MAX_DAILY_API_SPEND_USD": "2.00"}


def _load_existing() -> dict[str, str]:
    out: dict[str, str] = {}
    if not ENV.exists():
        return out
    for line in ENV.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def main() -> int:
    existing = _load_existing()
    print(f"\nSetting up {ENV}")
    print("Hidden input — your paste won't display. Press Enter to keep existing value.\n")

    out = dict(existing)
    for key, label in FIELDS:
        marker = "currently SET" if existing.get(key) else "currently MISSING"
        val = getpass.getpass(f"  {label} [{marker}]: ")
        if val.strip():
            out[key] = val.strip()

    for k, v in DEFAULTS.items():
        out.setdefault(k, v)

    # Atomic write so we never leave a half-written file on disk
    tmp_fd, tmp_path = tempfile.mkstemp(dir=ENV.parent, prefix=".env.", text=True)
    try:
        with os.fdopen(tmp_fd, "w") as f:
            f.write("# x-control credentials. Do not commit. chmod 600.\n")
            for k in [
                "XAPI_API_KEY",
                "X_OAUTH_CLIENT_ID",
                "X_OAUTH_CLIENT_SECRET",
                "MAX_DAILY_API_SPEND_USD",
            ]:
                if k in out:
                    f.write(f"{k}={out[k]}\n")
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, ENV)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    print(f"\n✓ wrote {ENV} (mode 0600)\n")
    for k, _label in FIELDS:
        status = "✓ set" if out.get(k) else "✗ MISSING — re-run to fill"
        print(f"  {k}: {status}")
    print(f"  MAX_DAILY_API_SPEND_USD: {out.get('MAX_DAILY_API_SPEND_USD', '(unset)')}")
    print()
    # XAPI_API_KEY is legacy and OK to leave blank; only treat OAuth pair as required.
    required = ("X_OAUTH_CLIENT_ID", "X_OAUTH_CLIENT_SECRET")
    missing = [k for k in required if not out.get(k)]
    if missing:
        print(f"⚠  {len(missing)} required field(s) still missing: {', '.join(missing)}.")
        return 1
    print("All credentials present. Next step:")
    print(f"  {Path(__file__).parent.parent}/.venv/bin/python "
          f"{Path(__file__).parent}/auth.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
