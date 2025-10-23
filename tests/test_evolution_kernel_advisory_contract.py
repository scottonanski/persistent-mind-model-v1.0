from __future__ import annotations
from pmm.runtime.evolution_kernel import EvolutionKernel
from pmm.runtime.policy.evolution import DEFAULT_POLICY

class SpyEventLog:
    def __init__(self): self.events=[]
    def read_tail(self, limit:int=1000): return self.events[-limit:]
    def read_after_id(self, after_id:int|None=None, limit:int=10000): return []
    def append(self, kind:str, content:str, meta:dict|None=None):
        self.events.append({"kind":kind,"content":content,"meta":meta or {}})
        return len(self.events)

class NoopTracker:
    def _open_map_all(self, _events): return {}

class AlwaysOKCooldown:
    def should_reflect(self, now:float, novelty:float): return True, "test"

def _k():  # factory with clean spies
    return EvolutionKernel(SpyEventLog(), NoopTracker(), AlwaysOKCooldown())

def test_evaluate_and_propose_do_not_append():
    ek = _k()
    before = len(ek.eventlog.events)
    _ = ek.evaluate_identity_evolution(events=[])
    _ = ek.propose_identity_adjustment(events=[])
    after = len(ek.eventlog.events)
    assert after == before, "EK must not append during evaluate/propose"

def test_trigger_reflection_may_append_only_reflection():
    ek = _k()
    # make evaluation ask for reflection and include a trait target
    def _fake_eval(**_):
        return {"reflection_needed": True, "trait_adjustments": {"conscientiousness": {"target": 0.6}}, "ias":0.2,"gas":0.2,"open_commitments":[]}
    ek.evaluate_identity_evolution = _fake_eval  # type: ignore[assignment]
    rid = ek.trigger_reflection_if_needed(events=[])
    assert isinstance(rid, int)
    kinds = [e["kind"] for e in ek.eventlog.events]
    assert kinds == ["reflection"], f"unexpected EK emissions: {kinds}"
