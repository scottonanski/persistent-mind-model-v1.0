from __future__ import annotations
import json
from pmm_v2.core.event_log import EventLog
from pmm_v2.core.rsm import RecursiveSelfModel


def test_rebuild_equals_incremental():
    log = EventLog(":memory:")
    rsm = RecursiveSelfModel(log)

    # Append events
    log.append(kind="user_message", content=json.dumps({"intent": "create"}), meta={})
    log.append(
        kind="reflection",
        content=json.dumps({"intent": "create", "next": "continue"}),
        meta={},
    )
    log.append(kind="commitment_open", content="c1", meta={"cid": "c1"})

    # Rebuild from full ledger
    rsm.rebuild()
    rebuild_snapshot = rsm.get_snapshot()

    # Incremental: new RSM, sync each event
    rsm_inc = RecursiveSelfModel(log)  # shares same log
    rsm_inc.snapshot = {
        "reflections": 0,
        "commitments": 0,
        "intents": {},
        "gaps": 0,
    }  # reset
    rsm_inc.last_score = None
    for event in log.read_all():
        rsm_inc.sync(event)
    rsm_inc.rebuild()  # Compute gaps

    assert rebuild_snapshot == rsm_inc.get_snapshot()


def test_detects_dominant_intent():
    log = EventLog(":memory:")
    rsm = RecursiveSelfModel(log)

    log.append(kind="user_message", content=json.dumps({"intent": "create"}), meta={})
    log.append(kind="user_message", content=json.dumps({"intent": "update"}), meta={})
    log.append(kind="user_message", content=json.dumps({"intent": "create"}), meta={})

    rsm.rebuild()
    snapshot = rsm.get_snapshot()
    assert snapshot["intents"]["create"] == 2
    assert snapshot["intents"]["update"] == 1


def test_identifies_knowledge_gap():
    log = EventLog(":memory:")
    rsm = RecursiveSelfModel(log)

    # Event 1: user wants "create"
    log.append(kind="user_message", content=json.dumps({"intent": "create"}), meta={})
    # Event 2: reflection responds with "continue" → no "create" in next → gap
    log.append(
        kind="reflection",
        content=json.dumps({"intent": "create", "next": "continue"}),
        meta={},
    )
    # Event 3: user wants "reflect"
    log.append(kind="user_message", content=json.dumps({"intent": "reflect"}), meta={})
    # Event 4: reflection responds with "reflect" → no gap
    log.append(
        kind="reflection",
        content=json.dumps({"intent": "reflect", "next": "reflect"}),
        meta={},
    )

    rsm.rebuild()
    snapshot = rsm.get_snapshot()
    assert snapshot["gaps"] == 1  # only first user intent not covered


def test_idempotent_no_emit_on_no_delta():
    log = EventLog(":memory:")
    rsm = RecursiveSelfModel(log)

    # Initial state: 1 reflection, 0 gaps → score = 0/2 = 0.0
    log.append(
        kind="reflection", content=json.dumps({"intent": "x", "next": "x"}), meta={}
    )
    rsm.rebuild()
    initial_events = len(log.read_all())

    # Sync same reflection again → no delta
    event = log.read_all()[-1]
    rsm.sync(event)

    assert len(log.read_all()) == initial_events  # no rsm_update


def test_emits_on_significant_change():
    log = EventLog(":memory:")

    # Build up reflections (score starts low)
    for _ in range(10):
        log.append(
            kind="reflection", content=json.dumps({"intent": "x", "next": "x"}), meta={}
        )
    _ = RecursiveSelfModel(log)  # rebuild emits rsm_update with score=0
    assert len([e for e in log.read_all() if e["kind"] == "rsm_update"]) == 1

    # Add user intent not covered → gap
    log.append(kind="user_message", content=json.dumps({"intent": "create"}), meta={})
    log.append(
        kind="reflection",
        content=json.dumps({"intent": "create", "next": "continue"}),
        meta={},
    )

    # Sync called automatically on append, should emit on second append
    rsm_updates = [e for e in log.read_all() if e["kind"] == "rsm_update"]
    assert len(rsm_updates) >= 2
