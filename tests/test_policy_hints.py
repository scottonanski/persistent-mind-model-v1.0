from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import AutonomyLoop
from pmm.runtime.cooldown import ReflectionCooldown


def _append_auto_tick(log: EventLog, ias: float, gas: float):
    log.append(
        kind="autonomy_tick",
        content="autonomy heartbeat",
        meta={
            "telemetry": {"IAS": float(ias), "GAS": float(gas)},
            "reflect": {"did": False, "reason": "test"},
        },
    )


def _list_policy_updates(events, component: str):
    return [
        e
        for e in events
        if e.get("kind") == "policy_update"
        and (e.get("meta") or {}).get("component") == component
    ]


def test_reflection_style_policy_update_on_stage_change(tmp_path):
    db = tmp_path / "policy1.db"
    log = EventLog(str(db))

    # Preload telemetry - but actual computation will determine real stage
    for _ in range(2):
        _append_auto_tick(log, ias=0.80, gas=0.70)

    loop = AutonomyLoop(
        eventlog=log, cooldown=ReflectionCooldown(), interval_seconds=0.01
    )
    loop.tick()

    events = log.read_all()
    # The tick computes actual IAS/GAS values from events, likely resulting in S0 stage
    # Check that we get a reflection_style policy update (actual value depends on computed stage)
    # Current implementation emits reflection cadence policy updates (component="reflection")
    pols = _list_policy_updates(events, component="reflection")
    assert pols, "expected a reflection cadence policy update"
    params = (pols[-1].get("meta") or {}).get("params") or {}
    # Verify cadence schema
    assert set(params.keys()) == {"min_turns", "min_time_s", "force_reflect_if_stuck"}


def test_recall_budget_policy_update_on_stage_change(tmp_path):
    db = tmp_path / "policy2.db"
    log = EventLog(str(db))

    # Preload telemetry - but actual computation will determine real stage
    for _ in range(2):
        _append_auto_tick(log, ias=0.60, gas=0.40)

    loop = AutonomyLoop(
        eventlog=log, cooldown=ReflectionCooldown(), interval_seconds=0.01
    )
    loop.tick()

    events = log.read_all()
    # Current implementation emits drift multiplier policy updates (component="drift")
    pols = _list_policy_updates(events, component="drift")
    assert pols, "expected a drift policy update"
    params = (pols[-1].get("meta") or {}).get("params") or {}
    # Verify drift schema
    assert set((params.get("mult") or {}).keys()) == {
        "openness",
        "conscientiousness",
        "neuroticism",
    }


def test_idempotent_policy_updates(tmp_path):
    db = tmp_path / "policy3.db"
    log = EventLog(str(db))

    # Preload telemetry to yield S3 after tick adds computed values
    for _ in range(2):
        _append_auto_tick(log, ias=0.85, gas=0.75)

    loop = AutonomyLoop(
        eventlog=log, cooldown=ReflectionCooldown(), interval_seconds=0.01
    )
    loop.tick()
    # Run tick again without changing stage; should not emit duplicate identical policy_update
    loop.tick()

    events = log.read_all()
    refl_pols = _list_policy_updates(events, component="reflection")
    recall_pols = _list_policy_updates(events, component="drift")

    # Only one per component after two ticks if stage unchanged
    assert len(refl_pols) == 1
    assert len(recall_pols) == 1
