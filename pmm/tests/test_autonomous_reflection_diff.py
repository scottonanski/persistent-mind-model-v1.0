# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from unittest.mock import Mock
import json

from pmm.runtime.reflection_synthesizer import synthesize_reflection
from pmm.runtime.loop import RuntimeLoop
from pmm.adapters.dummy_adapter import DummyAdapter
from pmm.runtime.autonomy_kernel import KernelDecision


class MockEventLog:
    def __init__(self, events):
        self.events = events.copy()
        self.listeners = []

    def read_all(self):
        return self.events

    def append(self, **kwargs):
        event_id = len(self.events) + 1
        event = {"id": event_id, **kwargs}
        self.events.append(event)
        for listener in self.listeners:
            listener(event)
        return event_id

    def register_listener(self, listener):
        self.listeners.append(listener)

    def hash_sequence(self):
        # simple hash
        return hash(
            tuple((e["id"], e.get("kind"), e.get("content")) for e in self.events)
        )

    def get(self, event_id: int):
        for e in self.events:
            if e["id"] == event_id:
                return e
        return None


def test_autonomous_reflection_diff():
    """Test that user-turn and autonomous reflections produce different content."""
    mock_eventlog = Mock()
    events = [
        {"kind": "user_message", "content": "some intent"},
        {"kind": "assistant_message", "content": "some outcome"},
        {
            "kind": "metrics_turn",
            "content": "provider:dummy,model:none,in_tokens:1,out_tokens:1,lat_ms:0",
        },
        {"kind": "commitment_open", "meta": {"cid": "c1"}, "content": "commit 1"},
        {"kind": "commitment_open", "meta": {"cid": "c2"}, "content": "commit 2"},
    ]
    mock_eventlog.read_all.return_value = events
    mock_eventlog.append.return_value = 123

    # Test user-turn reflection
    synthesize_reflection(mock_eventlog, source="user_turn")
    call_args = mock_eventlog.append.call_args
    assert call_args[1]["kind"] == "reflection"
    content = json.loads(call_args[1]["content"])
    assert content["intent"] == "some intent"
    assert content["outcome"] == "some outcome"
    assert content["next"] == "continue"

    # ------------------------------------------------------------------
    # 1. No stale – fewer than threshold events after oldest commitment
    # ------------------------------------------------------------------
    events = [
        {"kind": "user_message", "id": 1, "content": "hi"},
        {"kind": "assistant_message", "id": 2, "content": "hello"},
        {"kind": "metrics_turn", "id": 3},
        {"kind": "commitment_open", "id": 4, "content": "c1", "meta": {"cid": "c1"}},
        {"kind": "commitment_open", "id": 5, "content": "c2", "meta": {"cid": "c2"}},
    ]
    log = MockEventLog(events)
    loop = RuntimeLoop(eventlog=log, adapter=DummyAdapter(), autonomy=True)
    # force a reflect (kernel decides after ~10 events, we have only 5)
    loop.autonomy.decide_next_action = lambda: KernelDecision("reflect", "", [])
    loop.run_tick(slot=0, slot_id="test")
    refl = [e for e in log.events if e["kind"] == "reflection"][-1]
    assert refl["kind"] == "reflection"
    payload = json.loads(refl["content"])
    assert payload["commitments_reviewed"] == 2
    assert payload["stale"] == 0

    # ------------------------------------------------------------------
    # 2. Stale – more than threshold events after oldest commitment
    # ------------------------------------------------------------------
    many_events = [{"kind": "autonomy_tick", "id": i} for i in range(6, 30)]  # 24 extra
    log = MockEventLog(events + many_events)
    loop = RuntimeLoop(eventlog=log, adapter=DummyAdapter(), autonomy=True)
    loop.autonomy.decide_next_action = lambda: KernelDecision("reflect", "", [])
    loop.run_tick(slot=0, slot_id="test")
    refl = [e for e in log.events if e["kind"] == "reflection"][-1]
    payload = json.loads(refl["content"])
    assert payload["commitments_reviewed"] == 2
    assert payload["stale"] == 1


def test_autonomous_reflection_auto_close_stale():
    """Auto-close engages only when >2 open and staleness exceeds threshold."""
    events = [
        {"kind": "user_message", "id": 1, "content": "hi"},
        {"kind": "assistant_message", "id": 2, "content": "hello"},
        {"kind": "metrics_turn", "id": 3},
        {"kind": "commitment_open", "id": 4, "content": "c1", "meta": {"cid": "c1"}},
        {"kind": "commitment_open", "id": 5, "content": "c2", "meta": {"cid": "c2"}},
        {"kind": "commitment_open", "id": 6, "content": "c3", "meta": {"cid": "c3"}},
        {"kind": "commitment_open", "id": 7, "content": "c4", "meta": {"cid": "c4"}},
    ]
    # 31 events after oldest (id 4): ids 5 to 35
    many_events = [
        {"kind": "autonomy_tick", "id": i} for i in range(8, 38)
    ]  # 30 extra, total >30 after 4
    log = MockEventLog(events + many_events)
    loop = RuntimeLoop(eventlog=log, adapter=DummyAdapter(), autonomy=True)
    loop.autonomy.decide_next_action = lambda: KernelDecision("reflect", "", [])
    loop.run_tick(slot=0, slot_id="test")

    # Assert commitment_close emitted for stale ones, reason updated
    close_events = [e for e in log.events if e["kind"] == "commitment_close"]
    assert len(close_events) == 4
    assert all(e["meta"]["reason"] == "auto_close_idle_opt" for e in close_events)

    # Reflection shows commitments reviewed based on pre-close state
    refl = [e for e in log.events if e["kind"] == "reflection"][-1]
    payload = json.loads(refl["content"])
    assert payload["commitments_reviewed"] == 4
    assert payload["stale"] == 1
