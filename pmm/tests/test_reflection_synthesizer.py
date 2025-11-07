from __future__ import annotations

import json

from pmm.core.event_log import EventLog
from pmm.runtime.reflection_synthesizer import synthesize_reflection
from pmm.core.commitment_manager import CommitmentManager


def test_synthesize_reflection_deterministic(tmp_path):
    db = tmp_path / "refl9.db"
    log = EventLog(str(db))
    # seed one turn
    log.append(kind="user_message", content="hello", meta={})
    log.append(kind="assistant_message", content="hi there", meta={})
    log.append(
        kind="metrics_turn",
        content="provider:dummy,model:,in_tokens:2,out_tokens:2,lat_ms:0",
        meta={},
    )

    r1_id = synthesize_reflection(log)
    # remove it and synthesize again to compare content determinism
    events = log.read_all()[:-1]
    # rebuild DB quickly by re-appending (keeps same content deterministically)
    log2 = EventLog(str(tmp_path / "refl9_b.db"))
    for e in events:
        log2.append(kind=e["kind"], content=e["content"], meta=e["meta"])
    r2_id = synthesize_reflection(log2)

    r1 = [e for e in log.read_all() if e["id"] == r1_id][0]
    r2 = [e for e in log2.read_all() if e["id"] == r2_id][0]
    assert r1["content"] == r2["content"]


def test_autonomy_reflection_has_source():
    log = EventLog(":memory:")
    synthesize_reflection(
        log, meta_extra={"source": "autonomy_kernel"}, staleness_threshold=20
    )
    ev = log.read_all()[-1]
    assert ev["meta"]["source"] == "autonomy_kernel"


def _seed_rsm_data(log: EventLog) -> None:
    for _ in range(4):
        log.append(
            kind="assistant_message",
            content="CLAIM: failed to reason about consciousness.",
            meta={"topic": "consciousness"},
        )
    log.append(
        kind="assistant_message",
        content="Determinism remains essential to the plan.",
        meta={},
    )
    for _ in range(5):
        log.append(kind="reflection", content="{}", meta={})


def _append_turn(log: EventLog) -> None:
    log.append(kind="user_message", content="Requesting update.", meta={})
    log.append(
        kind="assistant_message",
        content="Outcome follows determinism guidance.",
        meta={},
    )
    log.append(
        kind="metrics_turn",
        content="provider:dummy,model:,in_tokens:1,out_tokens:1,lat_ms:0",
        meta={},
    )


def test_reflection_includes_rsm_when_threshold_met():
    log = EventLog(":memory:")
    _seed_rsm_data(log)
    _append_turn(log)

    reflection_id = synthesize_reflection(log)
    reflection_event = next(e for e in log.read_all() if e["id"] == reflection_id)
    payload = json.loads(reflection_event["content"])
    assert (
        payload["self_model"]
        == "RSM: 2 determinism refs, 1 knowledge gaps (consciousness)"
    )


def test_rsm_absent_below_threshold():
    log = EventLog(":memory:")
    for _ in range(4):
        log.append(kind="reflection", content="{}", meta={})
    _append_turn(log)

    reflection_id = synthesize_reflection(log)
    reflection_event = next(e for e in log.read_all() if e["id"] == reflection_id)
    payload = json.loads(reflection_event["content"])
    assert "self_model" not in payload


def test_reflection_includes_internal_goal_when_active():
    log = EventLog(":memory:")
    cm = CommitmentManager(log)
    cid = cm.open_internal("test_goal", reason="test")
    _append_turn(log)

    reflection_id = synthesize_reflection(log)
    reflection_event = next(e for e in log.read_all() if e["id"] == reflection_id)
    payload = json.loads(reflection_event["content"])
    assert "internal_goals" in payload
    assert payload["internal_goals"] == [f"{cid} (test_goal)"]
