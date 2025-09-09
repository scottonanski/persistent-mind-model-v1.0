from pmm.storage.eventlog import EventLog
from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime


def test_runtime_uses_same_chat_for_both_paths(monkeypatch, tmp_path):
    db = tmp_path / "db.sqlite"
    log = EventLog(str(db))
    cfg = LLMConfig(
        provider="openai", model="gpt-4o", embed_provider=None, embed_model=None
    )
    rt = Runtime(cfg, log)

    counters = {"calls": 0}

    def fake_generate(msgs, **kw):
        counters["calls"] += 1
        return f"ok{counters['calls']}"

    monkeypatch.setattr(rt.chat, "generate", fake_generate)

    r1 = rt.handle_user("hi")
    r2 = rt.reflect("ctx")

    assert r1 == "ok1" and r2 == "ok2"
    events = log.read_all()
    assert [e["kind"] for e in events][-2:] == ["response", "reflection"]
    assert counters["calls"] == 2


def test_bridge_pass_through(monkeypatch, tmp_path):
    db = tmp_path / "db.sqlite"
    log = EventLog(str(db))
    cfg = LLMConfig(
        provider="openai", model="gpt-4o", embed_provider=None, embed_model=None
    )
    rt = Runtime(cfg, log)

    seen = {}

    def spy_generate(msgs, **kw):
        seen["msgs"] = msgs
        return "ok"

    monkeypatch.setattr(rt.chat, "generate", spy_generate)
    _ = rt.handle_user("hello")

    assert isinstance(seen["msgs"], list)
    assert seen["msgs"][0]["content"] == "hello"
