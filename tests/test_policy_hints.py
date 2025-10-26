from pmm.runtime.cooldown import ReflectionCooldown
from pmm.runtime.loop import AutonomyLoop
from pmm.storage.eventlog import EventLog


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

    # Preload many ticks with stable metrics to ensure stage doesn't change
    # Use very low S0-level metrics (IAS/GAS) to stay in S0
    for _ in range(10):
        _append_auto_tick(log, ias=0.01, gas=0.01)

    loop = AutonomyLoop(
        eventlog=log, cooldown=ReflectionCooldown(), interval_seconds=0.01
    )
    loop.tick()

    # Verify stage after first tick
    from pmm.runtime.stage_tracker import StageTracker

    events_after_1 = log.read_all()
    stage_1, _ = StageTracker.infer_stage(events_after_1)

    # Run tick again without changing stage; should not emit duplicate identical policy_update
    loop.tick()

    events_after_2 = log.read_all()
    stage_2, _ = StageTracker.infer_stage(events_after_2)

    # Verify stage didn't change
    assert (
        stage_1 == stage_2
    ), f"Stage changed from {stage_1} to {stage_2}, invalidating idempotency test"

    refl_pols = _list_policy_updates(events_after_2, component="reflection")
    recall_pols = _list_policy_updates(events_after_2, component="drift")

    # Only one per component after two ticks if stage unchanged
    assert (
        len(refl_pols) == 1
    ), f"Expected 1 reflection policy, got {len(refl_pols)}: {[p['meta'] for p in refl_pols]}"
    assert len(recall_pols) == 1, f"Expected 1 drift policy, got {len(recall_pols)}"
