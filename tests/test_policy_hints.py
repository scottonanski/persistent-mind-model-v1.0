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

    # Preload telemetry to yield S2
    for _ in range(3):
        _append_auto_tick(log, ias=0.60, gas=0.40)

    loop = AutonomyLoop(
        eventlog=log, cooldown=ReflectionCooldown(), interval_seconds=0.01
    )
    loop.tick()

    events = log.read_all()
    # Expect stage_update and a policy_update for reflection_style with arm=analytical
    pols = _list_policy_updates(events, component="reflection_style")
    assert pols, "expected a reflection_style policy update"
    params = (pols[-1].get("meta") or {}).get("params") or {}
    assert params.get("arm") == "analytical"


def test_recall_budget_policy_update_on_stage_change(tmp_path):
    db = tmp_path / "policy2.db"
    log = EventLog(str(db))

    # Preload telemetry to yield S1
    for _ in range(3):
        _append_auto_tick(log, ias=0.40, gas=0.25)

    loop = AutonomyLoop(
        eventlog=log, cooldown=ReflectionCooldown(), interval_seconds=0.01
    )
    loop.tick()

    events = log.read_all()
    pols = _list_policy_updates(events, component="recall")
    assert pols, "expected a recall policy update"
    params = (pols[-1].get("meta") or {}).get("params") or {}
    assert params.get("recall_budget") == 2


def test_idempotent_policy_updates(tmp_path):
    db = tmp_path / "policy3.db"
    log = EventLog(str(db))

    # Preload telemetry to yield S3
    for _ in range(3):
        _append_auto_tick(log, ias=0.72, gas=0.56)

    loop = AutonomyLoop(
        eventlog=log, cooldown=ReflectionCooldown(), interval_seconds=0.01
    )
    loop.tick()
    # Run tick again without changing stage; should not emit duplicate identical policy_update
    loop.tick()

    events = log.read_all()
    refl_pols = _list_policy_updates(events, component="reflection_style")
    recall_pols = _list_policy_updates(events, component="recall")

    # Only one per component after two ticks if stage unchanged
    assert len(refl_pols) == 1
    assert len(recall_pols) == 1
