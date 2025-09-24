import time

import pytest

from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import AutonomyLoop


def test_autonomy_loop_integration_real(tmp_path):
    db = tmp_path / "auto_integ.db"
    log = EventLog(str(db))

    # Use real cooldown and event flow
    from pmm.runtime.cooldown import ReflectionCooldown

    cooldown = ReflectionCooldown()
    loop = AutonomyLoop(eventlog=log, cooldown=cooldown, interval_seconds=0.05)

    try:
        loop.start()
        time.sleep(0.5)
    finally:
        loop.stop()

    events = log.read_all()
    kinds = [e["kind"] for e in events]
    print("\n[TEST TELEMETRY] Event log kinds:", kinds)
    # Check for key events
    assert "autonomy_tick" in kinds
    assert "reflection" in kinds
    assert "policy_update" in kinds
    assert "stage_update" in kinds
    # Print telemetry for each
    for e in events:
        if e["kind"] in {
            "reflection",
            "commitment_close",
            "stage_update",
            "policy_update",
        }:
            print(f"[TEST TELEMETRY] {e['kind']}: {e}")


def test_stage_progress_uses_computed_metrics(tmp_path, monkeypatch):
    db = tmp_path / "telemetry.db"
    log = EventLog(str(db))

    from pmm.runtime import loop as loop_mod
    from pmm.runtime.cooldown import ReflectionCooldown

    monkeypatch.setattr(loop_mod, "compute_ias_gas", lambda events: (0.75, 0.9))

    def fake_infer_stage(events):
        return (
            "S0",
            {
                "IAS_mean": 0.001,
                "GAS_mean": 0.05,
                "count": 10,
                "window": 10,
            },
        )

    def fake_with_hysteresis(cls, prev_stage, next_stage, snapshot, events):
        return False

    monkeypatch.setattr(
        loop_mod.StageTracker,
        "infer_stage",
        staticmethod(fake_infer_stage),
    )
    monkeypatch.setattr(
        loop_mod.StageTracker,
        "with_hysteresis",
        classmethod(fake_with_hysteresis),
    )

    loop = AutonomyLoop(
        eventlog=log,
        cooldown=ReflectionCooldown(),
        interval_seconds=0.05,
        bootstrap_identity=False,
    )

    loop.tick()

    events = log.read_all()
    stage_progress_events = [e for e in events if e.get("kind") == "stage_progress"]
    assert stage_progress_events, "Expected a stage_progress event to be emitted"
    latest_progress = stage_progress_events[-1]["meta"]
    assert latest_progress["IAS"] == pytest.approx(0.75)
    assert latest_progress["GAS"] == pytest.approx(0.9)

    autonomy_ticks = [e for e in events if e.get("kind") == "autonomy_tick"]
    assert autonomy_ticks, "Expected an autonomy_tick event to be emitted"
    telemetry = (autonomy_ticks[-1].get("meta") or {}).get("telemetry") or {}
    assert telemetry.get("IAS") == pytest.approx(0.75)
    assert telemetry.get("GAS") == pytest.approx(0.9)
