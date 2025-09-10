
import pytest

from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import AutonomyLoop
from pmm.runtime.loop import CADENCE_BY_STAGE
from pmm.runtime.stage_tracker import StageTracker


class _CDControlled:
    """Controllable cooldown stub to force skip or allow."""

    def __init__(self):
        self.last_ts = 0.0
        self.turns_since = 0
        self._mode = "skip"
        self._reason = "min_turns"

    def set_skip(self, reason: str = "min_turns"):
        self._mode = "skip"
        self._reason = reason

    def set_ok(self):
        self._mode = "ok"
        self._reason = "ok"

    def should_reflect(
        self,
        now=None,
        novelty: float = 1.0,
        *,
        override_min_turns=None,
        override_min_seconds=None,
    ):
        if self._mode == "ok":
            return (True, "ok")
        return (False, self._reason)

    def reset(self):
        pass

    def note_user_turn(self):
        self.turns_since += 1


@pytest.fixture
def log(tmp_path):
    return EventLog(str(tmp_path / "p2e.db"))


def _monkey_stage(monkeypatch, stages):
    """Monkeypatch StageTracker.infer_stage to iterate given stage sequence."""
    it = iter(stages)

    def _fake_infer(events):
        try:
            st = next(it)
        except StopIteration:
            st = stages[-1]
        # minimal snapshot
        return st, {"IAS_mean": 0.0, "GAS_mean": 0.0, "count": 10, "window": 10}

    monkeypatch.setattr(StageTracker, "infer_stage", staticmethod(_fake_infer))


def _get_policy_updates(events):
    return [
        e
        for e in events
        if e.get("kind") == "policy_update"
        and (e.get("meta") or {}).get("component") == "reflection"
    ]


def _get_reflect_skips(events):
    return [
        e
        for e in events
        if e.get("kind") == "debug" and (e.get("meta") or {}).get("reflect_skip")
    ]


def _get_reflections(events):
    return [e for e in events if e.get("kind") == "reflection"]


def test_cadence_applies_by_stage(log, monkeypatch):
    _monkey_stage(monkeypatch, ["S0", "S1", "S2"])  # drive stage changes per tick

    loop = AutonomyLoop(eventlog=log, cooldown=_CDControlled(), interval_seconds=0.01)

    # First tick at S0 -> should emit policy_update with S0 params
    loop.tick()
    # Second tick at S1 -> new policy_update emitted with S1 params
    loop.tick()
    # Third tick at S2 -> new policy_update emitted with S2 params
    loop.tick()

    events = log.read_all()
    pus = _get_policy_updates(events)
    assert len(pus) == 3
    stages = [pu["meta"]["stage"] for pu in pus]
    assert stages == ["S0", "S1", "S2"]
    # Params match table
    for pu in pus:
        st = pu["meta"]["stage"]
        params = pu["meta"]["params"]
        expected = CADENCE_BY_STAGE[st]
        assert params["min_turns"] == expected["min_turns"]
        assert params["min_time_s"] == expected["min_time_s"]
        assert params["force_reflect_if_stuck"] == expected["force_reflect_if_stuck"]


def test_force_reflect_when_stuck_s0_s1_only(log, monkeypatch):
    # Provide exact 4-tick blocks for S0, S1, then S2 so each loop operates entirely within a stage
    _monkey_stage(monkeypatch, ["S0"] * 4 + ["S1"] * 4 + ["S2"] * 6)

    cd = _CDControlled()
    cd.set_skip("min_turns")  # ensure maybe_reflect records reflect_skip
    loop = AutonomyLoop(eventlog=log, cooldown=cd, interval_seconds=0.01)

    # Build 4 consecutive reflect_skip events in S0
    for _ in range(4):
        loop.tick()
    # Should have forced one reflection by now (S0 allows forcing)
    evs = log.read_all()
    refls = _get_reflections(evs)
    assert len(refls) >= 1

    # Continue in S1: create 4 more consecutive skips to trigger S1 forcing
    for _ in range(4):
        loop.tick()
    evs2 = log.read_all()
    refls2 = _get_reflections(evs2)
    assert len(refls2) >= 2  # another forced reflection in S1

    # Now stage moves to S2 where forcing is disabled; create 4 skips and ensure no extra forced reflection counted
    for _ in range(4):
        loop.tick()
    evs3 = log.read_all()
    refls3 = _get_reflections(evs3)
    # The count should remain the same as after S1 forcing (no new forced reflection in S2)
    assert len(refls3) == len(refls2)


def test_policy_update_idempotent(log, monkeypatch):
    # Keep stage constant at S1 across many ticks
    _monkey_stage(monkeypatch, ["S1"] * 10)
    cd = _CDControlled()
    cd.set_skip(
        "min_time"
    )  # cause skip so no reflection; but we only care about policy_update emissions
    loop = AutonomyLoop(eventlog=log, cooldown=cd, interval_seconds=0.01)

    # First tick emits policy_update for S1
    loop.tick()
    # Next ticks should not emit duplicate policy_update as params unchanged
    for _ in range(5):
        loop.tick()

    events = log.read_all()
    pus = _get_policy_updates(events)
    assert len(pus) == 1
    pu = pus[0]
    assert pu["meta"]["stage"] == "S1"
    assert pu["meta"]["params"] == CADENCE_BY_STAGE["S1"]
