from __future__ import annotations

from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import AutonomyLoop


def test_bias_event_emitted_once_and_before_choice_in_reflect_path(tmp_path):
    db = tmp_path / "biastrace.db"
    log = EventLog(str(db))

    class _CDOK:
        def should_reflect(self, **kw):
            return (True, "ok")

        def reset(self):
            pass

    loop = AutonomyLoop(eventlog=log, cooldown=_CDOK(), interval_seconds=0.01)
    loop.tick()

    evs = log.read_all()
    bias = [e for e in evs if e.get("kind") == "bandit_guidance_bias"]
    chosen = [e for e in evs if e.get("kind") == "bandit_arm_chosen"]

    assert len(bias) == 1
    assert len(chosen) == 1
    assert int(bias[0].get("id") or 0) < int(chosen[0].get("id") or 0)

    # meta.delta should include all arms and be bounded
    from pmm.runtime.reflection_bandit import ARMS, EPS_BIAS

    delta = (bias[0].get("meta") or {}).get("delta") or {}
    assert set(delta.keys()) == set(ARMS)
    assert all(abs(float(v)) <= EPS_BIAS for v in delta.values())

    # Unknown/missing type/score should produce zero deltas; simulate by emitting a bias with empty items
    # We don't control the internal builder here, but we can assert the structure holds.
