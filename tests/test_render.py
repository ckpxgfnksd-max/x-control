"""Smoke tests for digest + diagnose rendering against persona fixtures.

These don't pin every line of output — they assert the renderers don't crash
on representative inputs and that required sections appear when the data
warrants them."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "bench" / "fixtures"


def _load(persona: str) -> dict:
    return json.loads((FIXTURES / f"{persona}.json").read_text())


@pytest.mark.parametrize("persona", ["cold-start", "heavy-replier", "burst-poster"])
def test_digest_renders(persona):
    from scripts.monitor import PulseData
    from scripts.digest import render
    raw = _load(persona)["pulse_data"]
    raw = dict(raw)
    raw["today"] = date.fromisoformat(raw["today"])
    data = PulseData(**raw)
    out = render(data)
    assert isinstance(out, str)
    assert "# X Pulse" in out
    # Status line is mandatory.
    assert "status:" in out


def test_burst_poster_tail_section_renders():
    """burst-poster fixture has a tail array — verify the renderer emits it."""
    from scripts.monitor import PulseData
    from scripts.digest import render
    raw = _load("burst-poster")["pulse_data"]
    raw = dict(raw)
    raw["today"] = date.fromisoformat(raw["today"])
    data = PulseData(**raw)
    out = render(data)
    assert "24-80h tail" in out, "tail section header missing"
    assert "growing" in out
    assert "needs-rework" in out


def test_cold_start_no_tail_section():
    """cold-start has no tail data — the section should be omitted, not '(0)'."""
    from scripts.monitor import PulseData
    from scripts.digest import render
    raw = _load("cold-start")["pulse_data"]
    raw = dict(raw)
    raw["today"] = date.fromisoformat(raw["today"])
    data = PulseData(**raw)
    out = render(data)
    assert "24-80h tail" not in out


@pytest.mark.parametrize("persona", ["cold-start", "heavy-replier", "burst-poster"])
def test_diagnose_renders(persona, monkeypatch):
    """diagnose.render() should produce output for each persona without crashing."""
    fixture = _load(persona)
    events = fixture.get("tracker_events", [])
    # Monkeypatch events_in_last so diagnose's tracker import sees fixture data.
    from scripts import tracker, diagnose
    monkeypatch.setattr(tracker, "events_in_last", lambda hours: events)
    stats = diagnose._own_stats(fixture["pulse_data"])
    out = diagnose.render(fixture["pulse_data"], stats, {"events": events})
    assert isinstance(out, str)
    assert "# Algo diagnosis" in out


def test_diagnose_burst_poster_triggers_S19():
    """burst-poster fixture has angle_type='take' monoculture → S19 should fire."""
    from scripts import tracker, diagnose
    fixture = _load("burst-poster")
    events = fixture["tracker_events"]
    stats = diagnose._own_stats(fixture["pulse_data"])
    out = diagnose.render(fixture["pulse_data"], stats, {"events": events})
    # S19 looks for missing data/contrarian angles
    assert "S19" in out
    assert "Angle diversity" in out
