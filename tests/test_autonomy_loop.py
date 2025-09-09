import time

from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import AutonomyLoop


def test_autonomy_loop_emits_tick(tmp_path):
    db = tmp_path / "auto.db"
    log = EventLog(str(db))

    # Small interval for the test
    loop = AutonomyLoop(
        eventlog=log, cooldown=None, interval_seconds=0.05
    )  # cooldown is required by type but not used directly

    # Provide a minimal cooldown-like object with required methods
    class _CD:
        def __init__(self):
            self._turns = 2
            self.last_ts = 0.0

        def should_reflect(self, now=None, novelty: float = 1.0):
            # Always allow reflection during test
            return (True, "ok")

        def reset(self):
            pass

    loop.cooldown = _CD()

    try:
        loop.start()
        time.sleep(0.2)
    finally:
        loop.stop()

    events = log.read_all()
    kinds = [e["kind"] for e in events]
    assert "autonomy_tick" in kinds
    # Find last autonomy_tick and validate IAS/GAS presence
    ticks = [e for e in events if e["kind"] == "autonomy_tick"]
    meta = ticks[-1]["meta"]
    tel = meta.get("telemetry", {})
    assert "IAS" in tel and "GAS" in tel
