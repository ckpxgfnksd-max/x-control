#!/usr/bin/env python3
"""Render diagnose.py output from a persona fixture for autoresearch iteration.

Each fixture is `{pulse_data: <_pulse_data shape>, tracker_events: [...]}`.
Monkey-patches `tracker.events_in_last` so diagnose stays unmodified.

Usage:
  python bench/diagnose_render.py --persona cold-start
  python bench/diagnose_render.py --persona heavy-replier --out /tmp/x.md
  python bench/diagnose_render.py --all --out-dir ~/.claude/tmp/.../round_00
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "bench" / "fixtures"
sys.path.insert(0, str(ROOT))

from scripts import tracker  # noqa: E402
from scripts import diagnose  # noqa: E402


def _patched_events_in_last(fixture_events: list[dict]):
    def _impl(hours: float) -> list[dict]:
        cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600
        out = []
        for e in fixture_events:
            try:
                dt = datetime.fromisoformat(e["ts"].replace("Z", "+00:00"))
            except (KeyError, ValueError):
                continue
            if dt.timestamp() >= cutoff:
                out.append(e)
        return out
    return _impl


def render_persona(persona: str) -> str:
    fixture_path = FIXTURES / f"{persona}.json"
    if not fixture_path.exists():
        raise SystemExit(f"no fixture: {fixture_path}")
    fixture = json.loads(fixture_path.read_text())
    pulse_data = fixture["pulse_data"]
    tracker_events = fixture.get("tracker_events", [])

    tracker.events_in_last = _patched_events_in_last(tracker_events)

    stats = diagnose._own_stats(pulse_data)
    ship_summary = {"events": tracker_events}
    return diagnose.render(pulse_data, stats, ship_summary)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", choices=["cold-start", "heavy-replier", "burst-poster"])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", help="single-persona output file (default: stdout)")
    ap.add_argument("--out-dir", help="--all mode: write <persona>.md into this dir")
    args = ap.parse_args()

    if args.all:
        out_dir = Path(args.out_dir).expanduser() if args.out_dir else None
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
        for p in ("cold-start", "heavy-replier", "burst-poster"):
            md = render_persona(p)
            if out_dir:
                (out_dir / f"{p}.md").write_text(md)
                print(f"wrote {out_dir / f'{p}.md'} ({len(md)} chars)")
            else:
                sys.stdout.write(f"\n\n========== {p} ==========\n\n")
                sys.stdout.write(md)
        return 0

    if not args.persona:
        ap.error("--persona or --all required")
    md = render_persona(args.persona)
    if args.out:
        Path(args.out).expanduser().write_text(md)
        print(f"wrote {args.out} ({len(md)} chars)")
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
