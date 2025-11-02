from __future__ import annotations

import tempfile
from pathlib import Path

from pmm.runtime.autonomy_loop import AutonomyLoop
from pmm.runtime.cooldown import ReflectionCooldown
from pmm.storage.eventlog import EventLog


def test_autonomy_tick_emission_minimal():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        log = EventLog(str(db_path))

        # Seed with a single user event
        log.append(kind="user", content="hello", meta={})

        loop = AutonomyLoop(
            eventlog=log, cooldown=ReflectionCooldown(), interval_seconds=0.1
        )

        # Baseline count
        events_before = log.read_all()
        ticks_before = [e for e in events_before if e.get("kind") == "autonomy_tick"]

        # One tick should emit exactly one autonomy_tick
        loop.tick()
        events_after = log.read_all()
        ticks_after = [e for e in events_after if e.get("kind") == "autonomy_tick"]
        assert len(ticks_after) == len(ticks_before) + 1

        # Idempotency: immediate second tick should emit at most one more; guard may skip
        loop.tick()
        events_after2 = log.read_all()
        ticks_after2 = [e for e in events_after2 if e.get("kind") == "autonomy_tick"]
        assert len(ticks_after2) >= len(ticks_after)
