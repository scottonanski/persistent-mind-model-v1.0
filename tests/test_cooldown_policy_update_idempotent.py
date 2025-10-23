from __future__ import annotations

from pmm.llm.factory import LLMConfig
from pmm.runtime.eventlog import EventLog
from pmm.runtime.loop import AutonomyLoop, Runtime


def test_cooldown_policy_update_once_across_ticks(tmp_path, monkeypatch):
    cfg = LLMConfig(provider="dummy", model="noop")
    eventlog = EventLog(str(tmp_path / "pmm-cooldown.db"))
    rt = Runtime(cfg, eventlog)

    def _fake_apply_policies(events, metrics, **kwargs):
        return ({"cooldown.novelty_threshold": 0.42}, "force same cooldown")

    from pmm.runtime import self_evolution as _se

    monkeypatch.setattr(
        _se.SelfEvolution, "apply_policies", staticmethod(_fake_apply_policies)
    )

    loop = AutonomyLoop(
        eventlog=rt.eventlog,
        cooldown=rt.cooldown,
        interval_seconds=0.01,
        runtime=rt,
    )
    loop.tick()
    loop.tick()

    evs = rt.eventlog.read_tail(limit=500)
    policy_updates = [
        e
        for e in evs
        if e.get("kind") == "policy_update"
        and (e.get("meta") or {}).get("component") == "cooldown"
    ]
    assert len(policy_updates) == 1
    meta = policy_updates[0].get("meta") or {}
    assert meta.get("component") == "cooldown"
    assert meta.get("stage") is not None
