from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import Runtime
from pmm.llm.factory import LLMConfig


class _DummyChat:
    def __init__(self, reply: str):
        self._reply = reply

    def generate(self, messages, temperature: float = 1.0, max_tokens: int = 256, **kw):
        return self._reply


def _runtime_with_dummy(eventlog: EventLog, reply: str, bans=None) -> Runtime:
    cfg = LLMConfig(provider="openai", model="gpt-4o-mini")
    rt = Runtime(cfg, eventlog, ngram_bans=bans)
    # Monkeypatch chat to avoid network
    rt.chat = _DummyChat(reply)
    return rt


def test_default_bans_filtering(tmp_path):
    log = EventLog(str(tmp_path / "db1.db"))
    rt = _runtime_with_dummy(log, "As an AI, I will help.")
    out = rt.handle_user("hi")
    assert out == "I will help."
    # Ensure logged response event is filtered (may not be last due to commitment_open)
    events = log.read_all()
    responses = [e for e in events if e.get("kind") == "response"]
    assert responses and responses[-1]["content"] == "I will help."


def test_custom_ban_file(tmp_path, monkeypatch):
    banfile = tmp_path / "bans.txt"
    banfile.write_text("extra phrase\n", encoding="utf-8")
    log = EventLog(str(tmp_path / "db2.db"))
    rt = _runtime_with_dummy(
        log, "This has an extra phrase inside.", bans=["extra phrase"]
    )  # pass directly
    out = rt.handle_user("hi")
    assert out == "This has an inside."
    events = log.read_all()
    responses = [e for e in events if e.get("kind") == "response"]
    assert responses and responses[-1]["content"] == "This has an inside."


def test_unrelated_text_remains(tmp_path):
    log = EventLog(str(tmp_path / "db3.db"))
    rt = _runtime_with_dummy(log, "Completely unrelated.")
    out = rt.handle_user("hi")
    assert out == "Completely unrelated."
    events = log.read_all()
    responses = [e for e in events if e.get("kind") == "response"]
    assert responses and responses[-1]["content"] == "Completely unrelated."
