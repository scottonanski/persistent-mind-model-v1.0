from __future__ import annotations
import tempfile
import os

from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import AutonomyLoop, ReflectionCooldown


def _tmpdb():
    fd, path = tempfile.mkstemp(prefix="pmm_ratchet_", suffix=".db")
    os.close(fd)
    return path


def test_monotonic_single_emit_and_gap():
    db = _tmpdb()
    log = EventLog(db)

    # Seed enough reflections to pass RATCHET_MIN_REFLECTIONS and a recent evaluation_report
    for _ in range(3):
        log.append("reflection", "R.", {})
    log.append(
        "evaluation_report",
        "",
        {
            "component": "performance",
            "metrics": {"novelty_same_ratio": 0.9, "bandit_accept_winrate": 0.1},
            "window": 200,
            "tick": 1,
        },
    )

    loop = AutonomyLoop(
        eventlog=log, cooldown=ReflectionCooldown(), interval_seconds=0.1
    )
    loop.tick()

    evs = list(log.read_all())
    ratchets = [
        e
        for e in evs
        if e["kind"] == "trait_update" and (e["meta"] or {}).get("reason") == "ratchet"
    ]
    assert len(ratchets) == 1
    delta = (ratchets[0]["meta"] or {}).get("delta") or {}
    # Each delta should be in increments of 0.01 by design (or zero)
    for v in delta.values():
        assert abs(float(v)) in {0.0, 0.01}

    # Second tick should NOT emit a new ratchet due to RATCHET_MIN_TICK_GAP
    loop.tick()
    evs2 = list(log.read_all())
    ratchets2 = [
        e
        for e in evs2
        if e["kind"] == "trait_update" and (e["meta"] or {}).get("reason") == "ratchet"
    ]
    assert len(ratchets2) == 1
