from __future__ import annotations

from pmm.llm.factory import LLMConfig
from pmm.runtime.cooldown import ReflectionCooldown
from pmm.runtime.eventlog import EventLog
from pmm.runtime.loop import AutonomyLoop, Runtime


class FakeKernel:
    def __init__(self, proposal):
        self._proposal = dict(proposal)

    def evaluate_identity_evolution(self, **_):
        # say reflection not needed; provide trait target
        return {
            "trait_adjustments": {"conscientiousness": {"target": 0.62}},
            "reflection_needed": False,
        }

    def propose_identity_adjustment(self, **_):
        # stable proposal → same digest each time
        return dict(self._proposal)


def _collect_identity_adjust_proposals(events):
    return [e for e in events if e.get("kind") == "identity_adjust_proposal"]


def test_one_identity_adjust_proposal_per_tick(tmp_path):
    cfg = LLMConfig(provider="dummy", model="noop")
    eventlog = EventLog(str(tmp_path / "pmm.db"))
    rt = Runtime(cfg, eventlog)
    rt.cooldown = ReflectionCooldown()

    proposal = {
        "traits": {"conscientiousness": 0.62},
        "context": {"note": "stable"},
        "reason": "test",
    }
    rt.evolution_kernel = FakeKernel(proposal)

    loop = AutonomyLoop(
        eventlog=rt.eventlog,
        cooldown=rt.cooldown,
        interval_seconds=0.01,
        runtime=rt,
    )

    loop.tick()
    loop.tick()

    evs = rt.eventlog.read_tail(limit=200)
    proposals = _collect_identity_adjust_proposals(evs)
    assert len(proposals) == 1, f"expected 1 proposal, saw {len(proposals)}"
