from unittest.mock import Mock

from pmm_v2.runtime.reflection_synthesizer import synthesize_reflection
from pmm_v2.runtime.loop import RuntimeLoop
from pmm_v2.adapters.dummy_adapter import DummyAdapter
from pmm_v2.runtime.autonomy_kernel import KernelDecision


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
    content = call_args[1]["content"]
    assert content.startswith("{intent:'some intent'")

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
    refl = log.events[-1]
    assert refl["kind"] == "reflection"
    assert "commitments_reviewed:2" in refl["content"]
    assert "stale:0" in refl["content"]

    # ------------------------------------------------------------------
    # 2. Stale – more than threshold events after oldest commitment
    # ------------------------------------------------------------------
    many_events = [{"kind": "autonomy_tick", "id": i} for i in range(6, 30)]  # 24 extra
    log = MockEventLog(events + many_events)
    loop = RuntimeLoop(eventlog=log, adapter=DummyAdapter(), autonomy=True)
    loop.autonomy.decide_next_action = lambda: KernelDecision("reflect", "", [])
    loop.run_tick(slot=0, slot_id="test")
    refl = log.events[-1]
    assert "commitments_reviewed:2" in refl["content"]
    assert "stale:1" in refl["content"]
