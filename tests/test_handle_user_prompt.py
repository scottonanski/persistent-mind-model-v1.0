from pmm.runtime.loop import Runtime
from pmm.storage.eventlog import EventLog
from pmm.llm.factory import LLMConfig


def test_handle_user_injects_pmm_prompt(monkeypatch):
    # Create necessary objects for Runtime initialization
    cfg = LLMConfig(provider="openai", model="gpt-4o")
    eventlog = EventLog(":memory:")  # Use in-memory database for testing
    rt = Runtime(cfg, eventlog)

    captured = {}

    def fake_send(msgs, **kwargs):
        captured["msgs"] = msgs
        return "ok"

    monkeypatch.setattr(rt.chat, "generate", fake_send)

    rt.handle_user("Hello")

    # Check that a system message is injected
    system_msgs = [m for m in captured["msgs"] if m["role"] == "system"]
    assert system_msgs, "No system message injected"

    # Check that user message is present in the captured messages
    user_msgs = [
        m for m in captured["msgs"] if m["role"] == "user" and m["content"] == "Hello"
    ]
    assert user_msgs, "User message not found in captured messages"
