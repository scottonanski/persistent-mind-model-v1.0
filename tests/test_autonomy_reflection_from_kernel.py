from __future__ import annotations

from pmm.llm.factory import LLMConfig
from pmm.runtime.cooldown import ReflectionCooldown
from pmm.runtime.eventlog import EventLog
from pmm.runtime.loop import AutonomyLoop, Runtime


class FakeKernel:
    def __init__(self, eventlog):
        self.eventlog = eventlog

    def evaluate_identity_evolution(self, **_):
        return {
            "trait_adjustments": {"conscientiousness": {"target": 0.61}},
            "reflection_needed": True,
        }

    def propose_identity_adjustment(self, **_):
        self.eventlog.append(
            "reflection",
            "",
            {
                "source": "evolution_kernel",
                "reason": "policy_thresholds",
                "targets_summary": "conscientiousness:0.61",
            },
        )
        return None


def _collect(evs, kind):
    return [e for e in evs if e.get("kind") == kind]


def test_kernel_forces_reflection_with_targets_summary(tmp_path):
    cfg = LLMConfig(provider="dummy", model="noop")
    eventlog = EventLog(str(tmp_path / "pmm-test.db"))
    rt = Runtime(cfg, eventlog)
    rt.cooldown = ReflectionCooldown()

    rt.evolution_kernel = FakeKernel(rt.eventlog)

    loop = AutonomyLoop(
        eventlog=rt.eventlog,
        cooldown=rt.cooldown,
        interval_seconds=0.01,
        runtime=rt,
    )
    loop.tick()

    evs = rt.eventlog.read_tail(limit=200)
    refl = _collect(evs, "reflection")
    assert refl, "no reflection events recorded"
    assert any(
        "targets_summary" in (ev.get("meta") or {})
        and "conscientiousness" in (ev.get("meta") or {}).get("targets_summary", "")
        for ev in refl
    )
