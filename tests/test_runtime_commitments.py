from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model
from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime


def _mk_rt(tmp_path):
    db = tmp_path / "rt.db"
    log = EventLog(str(db))
    cfg = LLMConfig(
        provider="openai", model="gpt-4o", embed_provider=None, embed_model=None
    )
    return Runtime(cfg, log), log


def test_runtime_opens_commitment_from_reply(tmp_path, monkeypatch):
    rt, log = _mk_rt(tmp_path)

    def fake_generate(msgs, **kw):
        return "Okay, I will write the probe docs."

    monkeypatch.setattr(rt.chat, "generate", fake_generate)
    out = rt.handle_user("hi")
    assert "Okay," in out
    model = build_self_model(log.read_all())
    open_map = model.get("commitments", {}).get("open", {})
    assert len(open_map) >= 1  # at least one commitment opened


def test_runtime_closes_with_text_only_evidence(tmp_path, monkeypatch):
    rt, log = _mk_rt(tmp_path)

    # 1) open a commitment
    def gen_open(msgs, **kw):
        return "I will summarize the meeting."

    monkeypatch.setattr(rt.chat, "generate", gen_open)
    rt.handle_user("hi")

    # 2) emit Done: reply (text-only); should close when text evidence allowed
    def gen_done(msgs, **kw):
        return "Done: summarized the meeting"

    monkeypatch.setattr(rt.chat, "generate", gen_done)
    rt.handle_user("follow-up")

    model = build_self_model(log.read_all())
    open_map = model.get("commitments", {}).get("open", {})
    assert len(open_map) == 0  # closed via text evidence


def test_runtime_opens_commitment_from_user_text(tmp_path, monkeypatch):
    rt, log = _mk_rt(tmp_path)

    def fake_generate(msgs, **kw):
        return "Acknowledged."

    monkeypatch.setattr(rt.chat, "generate", fake_generate)
    rt.handle_user("I will handle the release documentation tomorrow.")

    model = build_self_model(log.read_all())
    open_map = model.get("commitments", {}).get("open", {})
    assert any("release documentation" in c.get("text", "") for c in open_map.values())
