import types

import pytest

from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime
from pmm.storage.eventlog import EventLog


@pytest.fixture
def runtime_with_event(tmp_path):
    cfg = LLMConfig(provider="openai", model="gpt-4o")
    eventlog = EventLog(str(tmp_path / "ledger.db"))
    runtime = Runtime(cfg, eventlog)
    event_id = eventlog.append("response", "Stored ledger narrative.", {})
    return runtime, event_id


def test_deterministic_lookup_persists_turn(runtime_with_event, monkeypatch):
    runtime, event_id = runtime_with_event
    question = f"What was event #{event_id}?"

    def _raise_generate(self, *args, **kwargs):
        raise AssertionError("LLM generation should not run for deterministic lookup")

    monkeypatch.setattr(
        runtime, "_generate_reply", types.MethodType(_raise_generate, runtime)
    )

    reply = runtime.handle_user(question)

    expected = f"Event #{event_id}: Stored ledger narrative."
    assert reply == expected

    events = runtime.eventlog.read_all()

    assert any(ev["kind"] == "user" and ev["content"] == question for ev in events)

    response_events = [
        ev for ev in events if ev["kind"] == "response" and ev["content"] == reply
    ]
    assert response_events, "No response event logged for deterministic lookup"
    response_event = response_events[-1]

    meta = response_event.get("meta") or {}
    assert meta.get("epistemic_source") == "ledger_lookup"

    response_eid = response_event["id"]
    assert not any(
        ev["kind"] == "embedding_indexed"
        and (ev.get("meta") or {}).get("eid") == response_eid
        for ev in events
    ), "Deterministic response should skip embedding persistence"
    assert not any(ev["kind"] == "insight_scored" for ev in events)


def test_deterministic_lookup_streaming_persists_turn(runtime_with_event, monkeypatch):
    runtime, event_id = runtime_with_event
    question = f"Can you show me event #{event_id}?"

    def _raise_stream(self, *args, **kwargs):
        raise AssertionError("LLM streaming should not run for deterministic lookup")

    monkeypatch.setattr(
        runtime,
        "_generate_reply_streaming",
        types.MethodType(_raise_stream, runtime),
    )

    chunks = list(runtime.handle_user_stream(question))
    expected = [f"Event #{event_id}: Stored ledger narrative."]
    assert chunks == expected

    events = runtime.eventlog.read_all()
    assert any(ev["kind"] == "user" and ev["content"] == question for ev in events)

    response_events = [
        ev for ev in events if ev["kind"] == "response" and ev["content"] == expected[0]
    ]
    assert response_events, "No response event logged for deterministic streaming reply"
    response_event = response_events[-1]
    meta = response_event.get("meta") or {}
    assert meta.get("epistemic_source") == "ledger_lookup"

    response_eid = response_event["id"]
    assert not any(
        ev["kind"] == "embedding_indexed"
        and (ev.get("meta") or {}).get("eid") == response_eid
        for ev in events
    ), "Deterministic streaming response should skip embedding persistence"
    assert not any(ev["kind"] == "insight_scored" for ev in events)


def test_forced_reply_surfaces_in_followup_context(runtime_with_event, monkeypatch):
    runtime, event_id = runtime_with_event

    # Seed an initial turn so runtime has baseline context
    captured_first: list[list[dict]] = []

    def fake_generate(self, messages, **kwargs):
        captured_first.append(messages)
        return "ack"

    monkeypatch.setattr(
        runtime, "_generate_reply", types.MethodType(fake_generate, runtime)
    )
    runtime.handle_user("Hello there")
    captured_first.clear()

    # Ensure deterministic lookup bypasses LLM generation
    def raise_if_called(self, *args, **kwargs):
        raise AssertionError("LLM should not run for deterministic lookup")

    monkeypatch.setattr(
        runtime, "_generate_reply", types.MethodType(raise_if_called, runtime)
    )
    runtime.handle_user(f"What was event #{event_id}?")

    # Capture the follow-up generation context
    followup_msgs: list[list[dict]] = []

    def capture_followup(self, messages, **kwargs):
        followup_msgs.append(messages)
        return "All good"

    monkeypatch.setattr(
        runtime, "_generate_reply", types.MethodType(capture_followup, runtime)
    )
    runtime.handle_user("What did we just discuss?")

    assert (
        followup_msgs
    ), "Expected LLM generation to run for the follow-up conversational turn"

    flattened = "\n".join(
        str(entry.get("content") or "") for entry in followup_msgs[-1]
    )
    assert (
        f"Event #{event_id}" in flattened
    ), "Forced reply should surface in follow-up context messages"
    assert (
        "What was event" in flattened
    ), "User question about the event should surface in follow-up context messages"
