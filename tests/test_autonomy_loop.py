import time

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
