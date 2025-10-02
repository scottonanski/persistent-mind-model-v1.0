from __future__ import annotations

import os
import tempfile

from pmm.runtime.self_evolution import propose_trait_ratchet
from pmm.storage.eventlog import EventLog


def _tmpdb():
    fd, path = tempfile.mkstemp(prefix="pmm_ratchet_idem_", suffix=".db")
    os.close(fd)
    return path


def test_noop_when_already_at_bounds():
    db = _tmpdb()
    log = EventLog(db)

    # Seed >=3 reflections and a triggering performance report
    for _ in range(3):
        log.append("reflection", "R.", {})
    log.append(
        "evaluation_report",
        "",
        {
            "component": "performance",
            "metrics": {"novelty_same_ratio": 0.95, "bandit_accept_winrate": 0.10},
            "window": 200,
            "tick": 2,
        },
    )

    # Pre-set traits to S4 upper/lower bounds so any proposed deltas clamp to zero
    # Use a legacy single-trait path for simplicity and set low meta.tick to satisfy gap logic
    log.append(
        "trait_update", "", {"trait": "openness", "delta": 0.30, "tick": 1}
    )  # 0.5 -> 0.8
    log.append(
        "trait_update", "", {"trait": "conscientiousness", "delta": 0.25, "tick": 1}
    )  # 0.5 -> 0.75
    log.append(
        "trait_update", "", {"trait": "extraversion", "delta": -0.05, "tick": 1}
    )  # 0.5 -> 0.45

    # Now proposing at S4 should be a no-op
    out = propose_trait_ratchet(log, tick=10, stage="S4")
    assert out is None

    # Ensure no new ratchet event exists
    evs = list(log.read_all())
    ratchets = [
        e
        for e in evs
        if e["kind"] == "trait_update" and (e["meta"] or {}).get("reason") == "ratchet"
    ]
    assert len(ratchets) == 0
