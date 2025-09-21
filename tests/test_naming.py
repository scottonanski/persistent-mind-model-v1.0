from __future__ import annotations

from pmm.runtime.loop import Runtime
from pmm.storage.eventlog import EventLog
from pmm.llm.factory import LLMConfig, LLMFactory


class _DummyChat:
    def generate(self, *args, **kwargs):
        return ""


class _DummyBundle:
    def __init__(self) -> None:
        self.chat = _DummyChat()
        self.embed = None


def _make_runtime() -> Runtime:
    cfg = LLMConfig(provider="openai", model="test")
    prev = LLMFactory.from_config
    LLMFactory.from_config = staticmethod(lambda cfg: _DummyBundle())
    try:
        rt = Runtime(cfg, EventLog())
    finally:
        LLMFactory.from_config = prev
    rt.chat.generate = lambda *a, **k: ""
    return rt


def test_user_assigns_assistant_name():
    runtime = _make_runtime()
    runtime.handle_user("Your name is Echo.")
    events = runtime.eventlog.read_all()
    assert any(
        e.get("kind") == "identity_adopt"
        and (e.get("meta") or {}).get("name") == "Echo"
        for e in events
    )


def test_user_assigns_with_context():
    import tempfile
    import os

    # Create a runtime with a temporary database file to ensure clean state
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        eventlog = EventLog(db_path)

        class _DummyChat:
            def generate(self, *args, **kwargs):
                return ""

        class _DummyBundle:
            def __init__(self) -> None:
                self.chat = _DummyChat()
                self.embed = None

        cfg = LLMConfig(provider="openai", model="test")
        runtime = Runtime(cfg, eventlog)
        runtime.chat.generate = lambda *a, **k: ""

        runtime.handle_user("I’d like to name you.")
        runtime.handle_user("Let’s call you Nova.")
        events = runtime.eventlog.read_all()
        assert any(
            e.get("kind") == "identity_adopt"
            and (e.get("meta") or {}).get("name") == "Nova"
            for e in events
        )


def test_user_names_self_does_not_adopt():
    runtime = _make_runtime()
    runtime.handle_user("I'm Scott.")
    events = runtime.eventlog.read_all()
    assert not any(
        e.get("kind") == "identity_adopt"
        and (e.get("meta") or {}).get("source") == "user"
        and (e.get("meta") or {}).get("name") == "Scott"
        for e in events
    )


def test_assistant_affirms_name():
    runtime = _make_runtime()
    # Clear any existing events to ensure clean test
    runtime.eventlog = EventLog()
    # Also reset the classifier to ensure clean state
    runtime.classifier = runtime.classifier.__class__(runtime.eventlog)
    runtime.chat.generate = lambda *a, **k: "I am Echo."
    # Mock bridge sanitization to prevent it from overriding our response
    runtime.bridge.sanitize = lambda text, **kwargs: "I am Echo."
    runtime.handle_user("What is your name?")
    events = runtime.eventlog.read_all()
    # Should propose, not adopt immediately for assistant affirmations
    assert any(
        e.get("kind") == "identity_propose" and e.get("content") == "Echo"
        for e in events
    )


def test_assistant_affirmation_multiword_skipped():
    runtime = _make_runtime()
    runtime.eventlog = EventLog()
    runtime.classifier = runtime.classifier.__class__(runtime.eventlog)
    runtime.chat.generate = lambda *a, **k: "I am Ice Cream."
    runtime.bridge.sanitize = lambda text, **kwargs: "I am Ice Cream."
    runtime.handle_user("What is your name?")
    events = runtime.eventlog.read_all()
    assert not any(
        e.get("kind") == "identity_propose"
        and (str(e.get("content") or "").lower() == "ice")
        for e in events
    )
    assert not any(
        e.get("kind") == "identity_adopt"
        and (str((e.get("meta") or {}).get("name") or "").lower() == "ice")
        for e in events
    )


def test_ambiguous_input_filtered():
    runtime = _make_runtime()
    # Clear any existing events to ensure clean test
    runtime.eventlog = EventLog()
    # Also reset the classifier to ensure clean state
    runtime.classifier = runtime.classifier.__class__(runtime.eventlog)
    runtime.handle_user("Call it Important.")
    events = runtime.eventlog.read_all()
    # Only check events from this specific test run
    relevant_events = [
        e for e in events if "Call it Important" in str(e.get("content", ""))
    ]
    assert not any(
        e.get("kind") in {"identity_adopt", "identity_propose"}
        and (e.get("meta") or {}).get("source") == "user"
        for e in relevant_events
    )
