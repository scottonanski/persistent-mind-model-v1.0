# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

import time
from pmm.adapters.dummy_adapter import DummyAdapter
from pmm.core.event_log import EventLog
from pmm.runtime.loop import RuntimeLoop


def test_supervisor_starts_on_boot(tmp_path):
    """Test that autonomy supervisor starts on RuntimeLoop init and emits stimuli."""
    log = EventLog(":memory:")
    _ = RuntimeLoop(eventlog=log, adapter=DummyAdapter())
    # Wait a bit for supervisor to emit
    time.sleep(0.1)
    events = log.read_all()
    stimuli = [e for e in events if e.get("kind") == "autonomy_stimulus"]
    assert stimuli, "No autonomy_stimulus emitted on boot"


def test_no_cli_dependency():
    """Test that autonomy runs without CLI triggers."""
    log = EventLog(":memory:")
    _ = RuntimeLoop(eventlog=log, adapter=DummyAdapter())
    time.sleep(0.1)
    events = log.read_all()
    # Ensure no /tick or similar in content
    for e in events:
        assert "/tick" not in e.get("content", ""), "Autonomy wired to CLI"


def test_replay_equals_live():
    """Test that replay mode produces same autonomy events."""
    log = EventLog(":memory:")
    _ = RuntimeLoop(eventlog=log, adapter=DummyAdapter())
    time.sleep(0.1)
    live_events = log.read_all()

    replay_log = EventLog(":memory:")
    for e in live_events:
        replay_log.append(kind=e["kind"], content=e["content"], meta=e["meta"])

    replay_loop = RuntimeLoop(eventlog=replay_log, adapter=DummyAdapter(), replay=True)
    replay_events = replay_loop.run_turn("dummy")  # Should return existing

    # Compare autonomy-related events
    live_autonomy = [e for e in live_events if e["kind"].startswith("autonomy")]
    replay_autonomy = [e for e in replay_events if e["kind"].startswith("autonomy")]
    assert len(live_autonomy) == len(replay_autonomy)


def test_idempotent_slots():
    """Test that same slot doesn't emit multiple stimuli."""
    log = EventLog(":memory:")
    _ = RuntimeLoop(eventlog=log, adapter=DummyAdapter())
    time.sleep(0.5)  # Allow multiple ticks
    events = log.read_all()
    stimuli = [e for e in events if e.get("kind") == "autonomy_stimulus"]
    slot_ids = [e["meta"]["slot_id"] for e in stimuli]
    assert len(slot_ids) == len(set(slot_ids)), "Duplicate stimuli for same slot"
