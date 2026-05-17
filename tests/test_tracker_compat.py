"""Tracker backward-compat: pre-2026-05-17 state files must load cleanly,
new authoring-metadata fields must round-trip on write."""
from __future__ import annotations

import json


def test_old_state_loads_with_defaults(write_tracker_state, sample_tracker_state_old):
    """An event missing topic_tags / angle_type / etc must come back with safe defaults."""
    write_tracker_state(sample_tracker_state_old)
    from scripts import tracker
    events = tracker.events_in_last(hours=24 * 30)
    assert len(events) == 2
    for e in events:
        # Authoring-metadata defaults
        assert e["topic_tags"] == []
        assert e["angle_type"] is None
        assert e["audience_pool"] is None
        assert e["format_goal"] is None
        assert e["experiment_label"] is None
        # Pre-existing fields unchanged
        assert "ts" in e and "tweet_id" in e and "format" in e


def test_record_ship_roundtrip(tmp_state_dir):
    """record_ship() with new kwargs must persist them through load."""
    from scripts import tracker
    tracker.record_ship(
        tweet_id="t1",
        tweets=["A thread starts here.", "Second tweet.", "Third."],
        is_reply=False,
        topic_tags=["tokenomics", "defi"],
        angle_type="contrarian",
        audience_pool="in_network",
        format_goal="profile_clicks",
        experiment_label="exp-A",
    )
    events = tracker.events_in_last(hours=24)
    assert len(events) == 1
    e = events[0]
    assert e["tweet_id"] == "t1"
    assert e["topic_tags"] == ["tokenomics", "defi"]
    assert e["angle_type"] == "contrarian"
    assert e["audience_pool"] == "in_network"
    assert e["format_goal"] == "profile_clicks"
    assert e["experiment_label"] == "exp-A"
    assert e["format"] == "thread"
    assert e["tweet_count"] == 3


def test_record_ship_old_callsite_still_works(tmp_state_dir):
    """Calling record_ship() without the new kwargs must succeed and default."""
    from scripts import tracker
    tracker.record_ship(tweet_id="t2", tweets=["Single."], is_reply=False)
    events = tracker.events_in_last(hours=24)
    assert events[0]["topic_tags"] == []
    assert events[0]["angle_type"] is None


def test_topic_mix_aggregates_tags(tmp_state_dir, write_tracker_state):
    """topic_mix() rolls up across events that have topic_tags."""
    write_tracker_state({
        "events": [
            {"ts": "2026-05-15T09:00:00+00:00", "tweet_id": "a", "format": "thread",
             "lang": "en", "is_reply": False, "tweet_count": 4, "char_count": 800,
             "topic_tags": ["tokenomics", "defi"]},
            {"ts": "2026-05-16T09:00:00+00:00", "tweet_id": "b", "format": "standalone",
             "lang": "en", "is_reply": False, "tweet_count": 1, "char_count": 200,
             "topic_tags": ["defi"]},
        ]
    })
    from scripts import tracker
    mix = tracker.topic_mix(hours=24 * 30)
    assert mix.get("tokenomics") == 1
    assert mix.get("defi") == 2


def test_angle_mix(tmp_state_dir, write_tracker_state, sample_tracker_state_new):
    write_tracker_state(sample_tracker_state_new)
    from scripts import tracker
    mix = tracker.angle_mix(hours=24 * 30)
    assert mix.get("contrarian") == 1


def test_experiment_mix(tmp_state_dir, write_tracker_state, sample_tracker_state_new):
    write_tracker_state(sample_tracker_state_new)
    from scripts import tracker
    mix = tracker.experiment_mix(hours=24 * 30)
    assert "cn-thread-v2" in mix
    assert len(mix["cn-thread-v2"]) == 1


def test_tail_categorize_growing():
    from scripts.tail import categorize
    item = {"impression_count": 5000, "like_count": 60, "retweet_count": 8, "reply_count": 10, "age_h": 30}
    cat = categorize(item, None, median_imps=3000)
    assert cat == "growing"


def test_tail_categorize_needs_rework():
    from scripts.tail import categorize
    item = {"impression_count": 9000, "like_count": 5, "retweet_count": 1, "reply_count": 2, "age_h": 52}
    cat = categorize(item, None, median_imps=3000)
    assert cat == "needs-rework"


def test_tail_categorize_dead():
    from scripts.tail import categorize
    item = {"impression_count": 200, "like_count": 0, "retweet_count": 0, "reply_count": 0, "age_h": 70}
    cat = categorize(item, None, median_imps=3000)
    assert cat == "dead"


def test_tail_categorize_growing_via_delta():
    """Even without engagement, if impressions grew ≥20% vs prior snapshot, mark growing."""
    from scripts.tail import categorize
    item = {"impression_count": 5000, "like_count": 0, "retweet_count": 0, "reply_count": 0, "age_h": 70}
    prior = {"impression_count": 3500}
    cat = categorize(item, prior, median_imps=3000)
    assert cat == "growing"
