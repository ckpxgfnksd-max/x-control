#!/usr/bin/env python3
"""Re-render a pulse from a frozen _pulse_data JSON dump. Used by autoresearch
to iterate on digest.py without re-fetching data."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.monitor import PulseData    # noqa: E402
from scripts.digest import render        # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: render_only.py <pulse_data.json>")
        return 2
    src = Path(sys.argv[1]).expanduser()
    raw = json.loads(src.read_text())
    raw["today"] = date.fromisoformat(raw["today"])
    data = PulseData(**raw)
    sys.stdout.write(render(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
