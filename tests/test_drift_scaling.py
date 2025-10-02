import pytest

from pmm.runtime.loop import AutonomyLoop
from pmm.runtime.stage_tracker import StageTracker
from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_identity


class _CDAlwaysSkip:
    def __init__(self, reason="due_to_low_novelty"):
        self.reason = reason
        self.last_ts = 0.0
        self.turns_since = 99

    def should_reflect(
        self,
        now=None,
        novelty=1.0,
        *,
        override_min_turns=None,
        override_min_seconds=None,
    ):
        return (False, self.reason)

    def reset(self):
        pass


class _CDNoReflect:
    def __init__(self):
        self.last_ts = 0.0
        self.turns_since = 0

    def should_reflect(
        self,
        now=None,
        novelty=1.0,
        *,
        override_min_turns=None,
        override_min_seconds=None,
    ):
        return (False, "min_time")

    def reset(self):
        pass


def _monkey_stage(monkeypatch, stage_sequence):
    it = iter(stage_sequence)

    def _fake_infer(events):
        try:
            st = next(it)
        except StopIteration:
            st = stage_sequence[-1]
        return st, {"IAS_mean": 0.5, "GAS_mean": 0.5, "count": 10, "window": 10}

    monkeypatch.setattr(StageTracker, "infer_stage", staticmethod(_fake_infer))


def _adopt_identity(log: EventLog, name="Casey"):
    log.append(kind="identity_adopt", content=name, meta={"name": name})


def _get_policy_updates(events, component):
    return [
        e
        for e in events
        if e.get("kind") == "policy_update"
        and (e.get("meta") or {}).get("component") == component
    ]


def _get_trait_updates(events, trait):
    return [
        e
        for e in events
        if e.get("kind") == "trait_update"
        and (e.get("meta") or {}).get("trait") == trait
    ]


@pytest.fixture
def log(tmp_path):
    return EventLog(str(tmp_path / "drift.db"))


def test_stage_scaled_deltas(log, monkeypatch):
    _adopt_identity(log)
    # S1 to trigger Rule 2 (three low_novelty skips)
    _monkey_stage(monkeypatch, ["S1"] * 10)
    cd = _CDAlwaysSkip("due_to_low_novelty")
    loop = AutonomyLoop(eventlog=log, cooldown=cd, interval_seconds=0.01)

    # Keep at least one open commitment during S1 ticks to avoid triggering Rule 3 inadvertently
    log.append(
        kind="commitment_open", content="", meta={"cid": "c1", "text": "placeholder"}
    )

    # Create 3 low_novelty skips to satisfy Rule 2 and spacing
    for _ in range(3):
        loop.tick()
    events = log.read_all()
    ups = _get_trait_updates(events, "openness")
    assert ups, "Expected an openness trait_update from Rule 2"
    delta = float(ups[-1]["meta"]["delta"])
    # S1 multiplier openness=1.25 -> 0.02*1.25=0.025
    assert abs(delta - 0.025) < 1e-6

    # Now S3 and trigger Rule 3 (stable period). Need two prior autonomy_tick with zero open commitments.
    _monkey_stage(monkeypatch, ["S3"] * 10)
    # Close the dummy commitment before evaluating stability
    log.append(kind="commitment_close", content="", meta={"cid": "c1"})
    cd2 = _CDNoReflect()
    loop2 = AutonomyLoop(eventlog=log, cooldown=cd2, interval_seconds=0.01)
    # Ensure there are no open commitments in projection, then tick to create two autonomy_ticks
    loop2.tick()
    loop2.tick()
    loop2.tick()
    events2 = log.read_all()
    nus = _get_trait_updates(events2, "neuroticism")
    assert nus, "Expected a neuroticism trait_update from Rule 3"
    ndelta = float(nus[-1]["meta"]["delta"])
    # S3 multiplier neuroticism=0.80 -> -0.02*0.80=-0.016
    assert abs(ndelta - (-0.016)) < 1e-6


def test_policy_update_emitted_on_stage_change(log, monkeypatch):
    _adopt_identity(log)
    _monkey_stage(
        monkeypatch, ["S0", "S1", "S1", "S2"]
    )  # S0->S1 (change), then stable, then S2 (change)
    loop = AutonomyLoop(eventlog=log, cooldown=_CDNoReflect(), interval_seconds=0.01)

    # First tick S0
    loop.tick()
    # Second tick S1 (change)
    loop.tick()
    # Third tick S1 (no change)
    loop.tick()
    # Fourth tick S2 (change)
    loop.tick()

    events = log.read_all()
    pus = _get_policy_updates(events, "drift")
    # Expect exactly two updates: one for S0 initial and one for S1 change; another for S2 change
    # Depending on initial state, initial S0 is a change too.
    assert len(pus) >= 2
    stages = [pu["meta"]["stage"] for pu in pus]
    # Should include S1 and S2 at least
    assert "S1" in stages and "S2" in stages


def test_clamping_still_projection_only(log, monkeypatch):
    _adopt_identity(log)
    # Force repeated Rule 2 to try to push openness over 1.0; projection should clamp
    _monkey_stage(monkeypatch, ["S1"] * 50)
    cd = _CDAlwaysSkip("due_to_low_novelty")
    loop = AutonomyLoop(eventlog=log, cooldown=cd, interval_seconds=0.01)

    # Tick many times to emit multiple Rule 2 updates, spaced by rule's 5-tick guard
    for i in range(20):
        loop.tick()
    ident = build_identity(log.read_all())
    traits = ident.get("traits")
    # Clamping is projection-only, so all traits remain within [0,1]
    for v in traits.values():
        assert 0.0 <= float(v) <= 1.0
