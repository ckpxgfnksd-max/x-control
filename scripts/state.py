"""Per-day KOL snapshot store. Powers follower deltas and viral-detection windowing."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1] / "state"


def _path(d: date) -> Path:
    return ROOT / f"kol_snapshot_{d.isoformat()}.json"


def save(snapshot: dict[str, Any], on: date | None = None) -> Path:
    on = on or date.today()
    ROOT.mkdir(parents=True, exist_ok=True)
    p = _path(on)
    p.write_text(json.dumps(snapshot, indent=2, default=str))
    return p


def load_previous(today: date | None = None, max_lookback: int = 14) -> tuple[date, dict[str, Any]] | None:
    """Most recent snapshot strictly before `today`, scanning back up to max_lookback days."""
    today = today or date.today()
    for delta in range(1, max_lookback + 1):
        d = today - timedelta(days=delta)
        p = _path(d)
        if p.exists():
            try:
                return d, json.loads(p.read_text())
            except json.JSONDecodeError:
                continue
    return None
