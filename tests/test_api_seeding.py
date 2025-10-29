from __future__ import annotations

from pmm.api.companion import _seed_history_if_fresh
from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime
from pmm.storage.eventlog import EventLog


def test_api_seeding_appends_prior_history_once(tmp_path):
    db = tmp_path / "test.db"
    eventlog = EventLog(str(db))
    cfg = LLMConfig(provider="dummy", model="test")
    runtime = Runtime(cfg, eventlog)

    messages = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "How are you?"},
    ]

    seeded1 = _seed_history_if_fresh(runtime, messages)
    assert seeded1 is True

    events = eventlog.read_all()
    kinds = [e["kind"] for e in events]
    # Exactly one user and one response seeded; last user is not seeded
    assert kinds.count("user") == 1
    assert kinds.count("response") == 1

    # Idempotent: second call should not seed again
    seeded2 = _seed_history_if_fresh(runtime, messages)
    assert seeded2 is False
    events2 = eventlog.read_all()
    assert len(events2) == len(events)


def test_extract_conversation_history_respects_config(tmp_path, monkeypatch):
    # Create project-local config to set history window
    cfg_dir = tmp_path / ".pmm"
    cfg_dir.mkdir()
    # Write valid JSON with the knob
    (cfg_dir / "config.json").write_text('{"CHAT_HISTORY_TURNS": 4}')
    monkeypatch.chdir(tmp_path)

    from pmm.runtime.loop.handlers import extract_conversation_history

    # Build synthetic event stream: user/response alternating, ending with user
    events: list[dict] = []
    for i in range(12):
        if i % 2 == 0:
            events.append({"kind": "user", "content": f"u{i}"})
        else:
            events.append({"kind": "response", "content": f"a{i}"})

    history = extract_conversation_history(events)
    # Window should be exactly 4 messages
    assert len(history) == 4
