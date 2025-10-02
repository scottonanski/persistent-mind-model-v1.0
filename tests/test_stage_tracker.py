import datetime as dt

from pmm.runtime.cooldown import ReflectionCooldown
from pmm.runtime.loop import AutonomyLoop
from pmm.storage.eventlog import EventLog


def _auto(ias, gas, ts):
    return {
        "kind": "autonomy_tick",
        "content": "",
        "meta": {"telemetry": {"IAS": ias, "GAS": gas}},
        "ts": ts,
    }


def _refl(ias, gas, ts):
    return {
        "kind": "reflection",
        "content": "",
        "meta": {"telemetry": {"IAS": ias, "GAS": gas}},
        "ts": ts,
    }


def test_insufficient_data_no_stage_update(tmp_path):
    log = EventLog(str(tmp_path / "stg1.db"))
    now = dt.datetime.now(dt.UTC)
    # Only 1 existing telemetry point (tick adds 1 more = 2 total, still <3)
    evs = [
        _auto(0.4, 0.3, now.isoformat()),
    ]
    for e in evs:
        log.append(kind=e["kind"], content=e["content"], meta=e["meta"])
    loop = AutonomyLoop(
        eventlog=log, cooldown=ReflectionCooldown(), interval_seconds=0.01
    )
    loop.tick()
    events = log.read_all()
    assert not [
        e for e in events if e.get("kind") == "stage_update"
    ], "no stage update expected with <3 points"


def test_upward_transition_s1_to_s2(tmp_path):
    log = EventLog(str(tmp_path / "stg2.db"))
    # Prior stage S1
    log.append(
        kind="stage_update",
        content="",
        meta={"from": None, "to": "S1", "snapshot": {}, "reason": "manual-seed"},
    )
    # Seed ~10 points around IAS ~0.55, GAS ~0.40 (S2 bucket)
    for i in range(10):
        log.append(
            kind="autonomy_tick",
            content="",
            meta={"telemetry": {"IAS": 0.55, "GAS": 0.40}},
        )
    # The mean is already in S2; plus hysteresis requires +0.03; we're well above
    loop = AutonomyLoop(
        eventlog=log, cooldown=ReflectionCooldown(), interval_seconds=0.01
    )
    loop.tick()
    events = log.read_all()
    st = [e for e in events if e.get("kind") == "stage_update"]
    assert (
        st and st[-1]["meta"].get("from") == "S1" and st[-1]["meta"].get("to") == "S2"
    )


def test_downward_transition_s3_to_s2(tmp_path):
    log = EventLog(str(tmp_path / "stg3.db"))
    # Prior stage S3
    log.append(
        kind="stage_update",
        content="",
        meta={"from": None, "to": "S3", "snapshot": {}, "reason": "manual-seed"},
    )
    # Window dipping below S3 by > 0.03 (e.g., IAS 0.66, GAS 0.50 → S2 bucket)
    for i in range(10):
        log.append(
            kind="autonomy_tick",
            content="",
            meta={"telemetry": {"IAS": 0.66, "GAS": 0.50}},
        )
    loop = AutonomyLoop(
        eventlog=log, cooldown=ReflectionCooldown(), interval_seconds=0.01
    )
    loop.tick()
    events = log.read_all()
    st = [e for e in events if e.get("kind") == "stage_update"]
    assert (
        st and st[-1]["meta"].get("from") == "S3" and st[-1]["meta"].get("to") == "S2"
    )


def test_no_thrash_around_boundary(tmp_path):
    log = EventLog(str(tmp_path / "stg4.db"))
    # Prior stage S2
    log.append(
        kind="stage_update",
        content="",
        meta={"from": None, "to": "S2", "snapshot": {}, "reason": "manual-seed"},
    )
    # Fluctuate around boundary: IAS ~0.50±0.01, GAS ~0.35±0.01 (within ±0.02)
    vals = [(0.49, 0.36), (0.5, 0.35), (0.51, 0.34), (0.5, 0.35)] * 3
    for ias, gas in vals:
        log.append(
            kind="autonomy_tick",
            content="",
            meta={"telemetry": {"IAS": ias, "GAS": gas}},
        )
    loop = AutonomyLoop(
        eventlog=log, cooldown=ReflectionCooldown(), interval_seconds=0.01
    )
    loop.tick()
    events = log.read_all()
    # Only the seeded stage_update should be present
    st = [e for e in events if e.get("kind") == "stage_update"]
    assert len(st) == 1
    meta = st[-1]["meta"]
    assert meta.get("to") == "S2"
    # Event shape validation
    assert set(meta.keys()) >= {"from", "to", "snapshot", "reason"}
