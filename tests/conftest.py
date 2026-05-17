"""Shared pytest fixtures for x-control tests.

Isolates each test from the real state/ dir by pointing tracker + tail at a
temporary directory. Avoids any contamination of the user's live tracker."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def tmp_state_dir(tmp_path, monkeypatch):
    """Redirect tracker + tail state to a temp dir for the duration of the test."""
    state = tmp_path / "state"
    state.mkdir()
    from scripts import tracker, tail
    monkeypatch.setattr(tracker, "ROOT", state)
    monkeypatch.setattr(tracker, "TRACKER_FILE", state / "weekly_tracker.json")
    monkeypatch.setattr(tail, "ROOT", state)
    return state


@pytest.fixture
def sample_draft_text():
    return (
        "Most tokenomics threads miss the obvious thing: vesting cliffs don't "
        "matter if your buyback can't outpace emissions.\n\n"
        "Here's the math nobody publishes."
    )


@pytest.fixture
def sample_tracker_state_old():
    """Pre-2026-05-17 tracker state — events lack the authoring-metadata fields."""
    return {
        "events": [
            {
                "ts": "2026-05-10T09:00:00+00:00",
                "tweet_id": "old_001",
                "format": "standalone",
                "lang": "en",
                "is_reply": False,
                "tweet_count": 1,
                "char_count": 180,
            },
            {
                "ts": "2026-05-12T09:00:00+00:00",
                "tweet_id": "old_002",
                "format": "thread",
                "lang": "en",
                "is_reply": False,
                "tweet_count": 6,
                "char_count": 1240,
            },
        ]
    }


@pytest.fixture
def sample_tracker_state_new():
    """New-shape tracker state — events carry the authoring-metadata fields."""
    return {
        "events": [
            {
                "ts": "2026-05-15T09:00:00+00:00",
                "tweet_id": "new_001",
                "format": "thread",
                "lang": "en",
                "is_reply": False,
                "tweet_count": 8,
                "char_count": 1800,
                "topic_tags": ["tokenomics", "defi"],
                "angle_type": "contrarian",
                "audience_pool": "in_network",
                "format_goal": "profile_clicks",
                "experiment_label": "cn-thread-v2",
            },
        ]
    }


@pytest.fixture
def write_tracker_state(tmp_state_dir):
    """Factory: write a state dict to the temp tracker file."""

    def _write(state: dict) -> Path:
        path = tmp_state_dir / "weekly_tracker.json"
        path.write_text(json.dumps(state, indent=2))
        return path

    return _write
