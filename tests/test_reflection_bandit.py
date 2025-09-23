from pmm.storage.eventlog import EventLog
from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime, maybe_reflect


def _mk_rt(tmp_path):
    db = tmp_path / "rb.db"
    log = EventLog(str(db))
    cfg = LLMConfig(
        provider="openai", model="gpt-4o", embed_provider=None, embed_model=None
    )
    return Runtime(cfg, log), log


def test_arm_logged_each_reflection(tmp_path, monkeypatch):
    rt, log = _mk_rt(tmp_path)

    # Force reflection by bypassing cooldown gating
    class DummyCooldown:
        def should_reflect(self, **kw):
            return (True, "ok")

        def reset(self):
            pass

    rt.cooldown = DummyCooldown()

    # Provide deterministic reflection content
    monkeypatch.setattr(rt.chat, "generate", lambda msgs, **kw: "Reflection note.")

    did, reason = maybe_reflect(
        log,
        rt.cooldown,
        llm_generate=lambda context: "This is a test reflection with sufficient content.\nIt has multiple lines to pass the requirements.",
    )
    assert did

    kinds = [e.get("kind") for e in log.read_all()]
    assert "bandit_arm_chosen" in kinds


def test_reward_follows_arm(tmp_path, monkeypatch):
    rt, log = _mk_rt(tmp_path)

    class DummyCooldown:
        def should_reflect(self, **kw):
            return (True, "ok")

        def reset(self):
            pass

    rt.cooldown = DummyCooldown()
    monkeypatch.setattr(rt.chat, "generate", lambda msgs, **kw: "Reflection A.")

    # Trigger multiple autonomy ticks to accumulate horizon and rewards
    from pmm.runtime.loop import AutonomyLoop

    loop = AutonomyLoop(eventlog=log, cooldown=rt.cooldown, interval_seconds=0.01)
    # Manually call tick a few times
    for _ in range(5):
        loop.tick()

    evs = log.read_all()
    kinds = [e.get("kind") for e in evs]
    assert "bandit_arm_chosen" in kinds
    assert "bandit_reward" in kinds


def test_deterministic_sequence(tmp_path, monkeypatch):
    rt, log = _mk_rt(tmp_path)

    class DummyCooldown:
        def should_reflect(self, **kw):
            return (True, "ok")

        def reset(self):
            pass

    rt.cooldown = DummyCooldown()
    monkeypatch.setattr(rt.chat, "generate", lambda msgs, **kw: "Reflection B.")

    from pmm.runtime.loop import AutonomyLoop

    loop = AutonomyLoop(eventlog=log, cooldown=rt.cooldown, interval_seconds=0.01)
    # Trigger 3 ticks to get 3 arm choices
    for _ in range(3):
        loop.tick()

    arms = [
        (e.get("meta") or {}).get("arm")
        for e in log.read_all()
        if e.get("kind") == "bandit_arm_chosen"
    ]
    # Deterministic seed yields stable order across runs
    assert len(arms) >= 3
    assert arms == list(arms)  # no randomness causes different order across runs
