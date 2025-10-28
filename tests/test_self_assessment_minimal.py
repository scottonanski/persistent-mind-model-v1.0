from pmm.runtime.loop import (
    _apply_self_assessment_policies,
    _maybe_emit_self_assessment,
    _maybe_rotate_assessment_formula,
)
from pmm.storage.eventlog import EventLog


def _count(log: EventLog, kind: str) -> int:
    return sum(1 for e in log.read_all() if e.get("kind") == kind)


def test_self_assessment_bucket_idempotency(tmp_path):
    db = tmp_path / "sa_idem.db"
    log = EventLog(str(db))

    # 10 reflections → 1 self_assessment (idempotent by inputs_hash)
    for _ in range(10):
        log.append(kind="reflection", content="", meta={})
    _maybe_emit_self_assessment(log, window=10)
    _maybe_emit_self_assessment(log, window=10)  # should be a no-op
    events = log.read_all()
    sas = [e for e in events if e.get("kind") == "self_assessment"]
    assert len(sas) == 1
    m = sas[0].get("meta") or {}
    assert int(m.get("window", 0)) == 10
    assert isinstance(m.get("window_start_id"), int)
    assert isinstance(m.get("window_end_id"), int)
    ih = str(m.get("inputs_hash") or "")
    assert len(ih) == 64 and all(c in "0123456789abcdef" for c in ih)

    # +10 reflections → 2nd assessment
    for _ in range(10):
        log.append(kind="reflection", content="", meta={})
    _maybe_emit_self_assessment(log, window=10)
    assert _count(log, "self_assessment") == 2


def test_self_assessment_deadband_no_policy_update(tmp_path):
    db = tmp_path / "sa_deadband.db"
    log = EventLog(str(db))

    # Baseline policy (so cadence is well-defined)
    log.append(
        kind="policy_update",
        content="",
        meta={"component": "reflection", "params": {"min_turns": 2, "min_time_s": 20}},
    )
    # Append a self_assessment with metrics that do not trigger any change
    sa_id = log.append(
        kind="self_assessment",
        content="",
        meta={
            "window": 10,
            "opened": 0,
            "closed": 0,
            "actions": 0,
            "trait_delta_abs": 0.0,
            "efficacy": 0.4,  # middle range
            "avg_close_lag": 1.0,
            "hit_rate": 0.4,
            "drift_util": 0.0,
        },
    )
    # Deadband should suppress policy update (no branch triggers, deltas <10%)
    out = _apply_self_assessment_policies(log)
    assert out is None
    pus = [
        e
        for e in log.read_all()
        if e.get("kind") == "policy_update"
        and (e.get("meta") or {}).get("source") == "self_assessment"
        and (e.get("meta") or {}).get("assessment_id") == sa_id
    ]
    assert len(pus) == 0


def test_self_assessment_clamp_bounds(tmp_path):
    db = tmp_path / "sa_clamp.db"
    log = EventLog(str(db))

    # Scenario A: high performance → decrease, bounded at lower time floor of 30
    log.append(
        kind="policy_update",
        content="",
        meta={"component": "reflection", "params": {"min_turns": 2, "min_time_s": 11}},
    )
    log.append(
        kind="self_assessment",
        content="",
        meta={
            "window": 10,
            "opened": 5,
            "closed": 4,
            "actions": 5,
            "trait_delta_abs": 0.0,
            "efficacy": 0.8,
            "avg_close_lag": 2.0,
            "hit_rate": 0.8,
            "drift_util": 0.0,
        },
    )
    _apply_self_assessment_policies(log)
    pu1 = [
        e
        for e in log.read_all()
        if e.get("kind") == "policy_update"
        and (e.get("meta") or {}).get("source") == "self_assessment"
    ][-1]
    p1 = (pu1.get("meta") or {}).get("params") or {}
    assert 1 <= int(p1.get("min_turns", 0)) <= 10
    assert 30 <= int(p1.get("min_time_s", 0)) <= 120

    # Scenario B: low performance → increase, bounded by upper caps
    log.append(
        kind="policy_update",
        content="",
        meta={"component": "reflection", "params": {"min_turns": 6, "min_time_s": 270}},
    )
    log.append(
        kind="self_assessment",
        content="",
        meta={
            "window": 10,
            "opened": 10,
            "closed": 0,
            "actions": 1,
            "trait_delta_abs": 0.0,
            "efficacy": 0.0,
            "avg_close_lag": 12.0,
            "hit_rate": 0.0,
            "drift_util": 0.0,
        },
    )
    _apply_self_assessment_policies(log)
    pu2 = [
        e
        for e in log.read_all()
        if e.get("kind") == "policy_update"
        and (e.get("meta") or {}).get("source") == "self_assessment"
    ][-1]
    p2 = (pu2.get("meta") or {}).get("params") or {}
    assert int(p2.get("min_turns", 0)) == 7  # bounded increase within limits
    assert int(p2.get("min_time_s", 0)) == 120  # clamped at upper bound


def test_assessment_rotation_round_robin(tmp_path):
    db = tmp_path / "sa_rotate.db"
    log = EventLog(str(db))

    # Create reflections in three windows of 10, emitting one SA per bucket
    for _ in range(10):
        log.append(kind="reflection", content="", meta={})
    _maybe_emit_self_assessment(log, window=10)
    for _ in range(10):
        log.append(kind="reflection", content="", meta={})
    _maybe_emit_self_assessment(log, window=10)
    for _ in range(10):
        log.append(kind="reflection", content="", meta={})
    _maybe_emit_self_assessment(log, window=10)
    _maybe_rotate_assessment_formula(log)
    rot1 = [e for e in log.read_all() if e.get("kind") == "assessment_policy_update"][
        -1
    ]
    m1 = rot1.get("meta") or {}
    assert m1.get("formula") == "v1"
    assert int(m1.get("rotation_index", -1)) == 1

    # Add three more buckets → 6 SAs total; next rotation should be v2
    for _ in range(10):
        log.append(kind="reflection", content="", meta={})
    _maybe_emit_self_assessment(log, window=10)
    for _ in range(10):
        log.append(kind="reflection", content="", meta={})
    _maybe_emit_self_assessment(log, window=10)
    for _ in range(10):
        log.append(kind="reflection", content="", meta={})
    _maybe_emit_self_assessment(log, window=10)
    _maybe_rotate_assessment_formula(log)
    rot2 = [e for e in log.read_all() if e.get("kind") == "assessment_policy_update"][
        -1
    ]
    m2 = rot2.get("meta") or {}
    assert m2.get("formula") == "v2"
    assert int(m2.get("rotation_index", -1)) == 2
