from __future__ import annotations

import os
import tempfile

from pmm.runtime.evaluators.curriculum import maybe_propose_curriculum
from pmm.runtime.loop import AutonomyLoop, ReflectionCooldown
from pmm.storage.eventlog import EventLog


def _tmpdb():
    fd, path = tempfile.mkstemp(prefix="pmm_curr_", suffix=".db")
    os.close(fd)
    return path


def _mk(kind, meta=None, content=""):
    return {"kind": kind, "content": content, "meta": (meta or {})}


def _append_evaluation_report(log: EventLog, **metrics):
    return log.append(
        "evaluation_report",
        "",
        {
            "component": "performance",
            "metrics": metrics,
            "window": 200,
            "tick": 1,
        },
    )


def test_rule1_low_winrate_proposes_and_applies_once():
    db = _tmpdb()
    log = EventLog(db)

    # Seed prior reflection policy min_turns=3
    log.append(
        "policy_update", "", {"component": "reflection", "params": {"min_turns": 3}}
    )
    _append_evaluation_report(log, bandit_accept_winrate=0.10, novelty_same_ratio=0.10)

    # Propose
    eid = maybe_propose_curriculum(log, tick=7)
    assert isinstance(eid, int) and eid > 0

    # Bridge: simulate the loop bridge once
    loop = AutonomyLoop(
        eventlog=log, cooldown=ReflectionCooldown(), interval_seconds=0.1
    )
    # call only the bridging block by triggering a tick with no evaluator firing (we just need the bridge code path)
    loop.tick()

    # Verify policy_update applied exactly once with proposed params (min_turns decreased by 1 => 2)
    evs = list(log.read_all())
    applied = [
        e
        for e in evs
        if e["kind"] == "policy_update"
        and (e["meta"] or {}).get("component") == "reflection"
        and (e["meta"] or {}).get("params") == {"min_turns": 2}
    ]
    assert len(applied) == 1

    # Second tick should not duplicate
    loop.tick()
    evs2 = list(log.read_all())
    applied2 = [
        e
        for e in evs2
        if e["kind"] == "policy_update"
        and (e["meta"] or {}).get("component") == "reflection"
        and (e["meta"] or {}).get("params") == {"min_turns": 2}
    ]
    assert len(applied2) == 1


def test_rule2_high_sameness_proposes_and_applies_once():
    db = _tmpdb()
    log = EventLog(db)

    # Seed prior cooldown novelty_threshold=0.4
    log.append(
        "policy_update",
        "",
        {"component": "cooldown", "params": {"novelty_threshold": 0.4}},
    )
    _append_evaluation_report(log, bandit_accept_winrate=0.90, novelty_same_ratio=0.90)

    eid = maybe_propose_curriculum(log, tick=8)
    assert isinstance(eid, int) and eid > 0

    loop = AutonomyLoop(
        eventlog=log, cooldown=ReflectionCooldown(), interval_seconds=0.1
    )
    loop.tick()

    evs = list(log.read_all())
    applied = [
        e
        for e in evs
        if e["kind"] == "policy_update"
        and (e["meta"] or {}).get("component") == "cooldown"
        and (e["meta"] or {}).get("params") == {"novelty_threshold": 0.45}
    ]
    assert len(applied) == 1

    loop.tick()
    evs2 = list(log.read_all())
    applied2 = [
        e
        for e in evs2
        if e["kind"] == "policy_update"
        and (e["meta"] or {}).get("component") == "cooldown"
        and (e["meta"] or {}).get("params") == {"novelty_threshold": 0.45}
    ]
    assert len(applied2) == 1
