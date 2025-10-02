from __future__ import annotations

import os
import tempfile

from pmm.runtime.self_evolution import RATCHET_BOUNDS, propose_trait_ratchet
from pmm.storage.eventlog import EventLog


def _tmpdb():
    fd, path = tempfile.mkstemp(prefix="pmm_ratchet_stage_", suffix=".db")
    os.close(fd)
    return path


def test_bounds_per_stage_and_min_reflections():
    stages = ["S0", "S1", "S2", "S3", "S4"]
    for st in stages:
        db = _tmpdb()
        log = EventLog(db)
        # Seed >= RATCHET_MIN_REFLECTIONS and a performance report
        # that triggers both openness+ and conscientiousness+
        for _ in range(3):
            log.append("reflection", "R.", {})
        log.append(
            "evaluation_report",
            "",
            {
                "component": "performance",
                "metrics": {"novelty_same_ratio": 0.9, "bandit_accept_winrate": 0.1},
                "window": 200,
                "tick": 7,
            },
        )
        eid = propose_trait_ratchet(log, tick=10, stage=st)
        assert (eid is None) is False
        # After application, identity traits must be within stage bounds
        from pmm.storage.projection import build_identity

        ident = build_identity(log.read_all())
        traits = ident.get("traits") or {}
        b = RATCHET_BOUNDS[st]
        assert b["openness"][0] <= traits["openness"] <= b["openness"][1]
        assert (
            b["conscientiousness"][0]
            <= traits["conscientiousness"]
            <= b["conscientiousness"][1]
        )
        assert b["extraversion"][0] <= traits["extraversion"] <= b["extraversion"][1]

    # Requires >= RATCHET_MIN_REFLECTIONS
    db2 = _tmpdb()
    log2 = EventLog(db2)
    for _ in range(2):
        log2.append("reflection", "R.", {})
    log2.append(
        "evaluation_report",
        "",
        {
            "component": "performance",
            "metrics": {"novelty_same_ratio": 0.9, "bandit_accept_winrate": 0.1},
            "window": 200,
            "tick": 3,
        },
    )
    out = propose_trait_ratchet(log2, tick=10, stage="S2")
    assert out is None
