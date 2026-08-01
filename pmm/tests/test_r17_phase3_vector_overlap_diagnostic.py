# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""R17 Phase 3 — attributable at-most-once vector-overlap diagnostics.

Guarantee under test:

    For each eligible strict-v2 retrieval_selection, at most one canonical
    vector_overlap_diagnostic exists; that event names the selection; every
    write path enforces eligibility, schema, source, and uniqueness; the event
    is type-isolated from reflection.

Out of scope: hybrid reproduction, vector-stage verification, configuration-
driven retrieval, re-audit supersession.
"""

from __future__ import annotations

import json

import pytest

from pmm.core.event_log import (
    EventLog,
    VECTOR_OVERLAP_DIAGNOSTIC_KIND,
    VECTOR_OVERLAP_DIAGNOSTIC_PROTOCOL,
    VECTOR_OVERLAP_DIAGNOSTIC_SOURCE,
)
from pmm.core.meme_graph import MemeGraph
from pmm.core.rsm import RecursiveSelfModel
from pmm.runtime.autonomy_kernel import AutonomyKernel


def _seed_query(log: EventLog, query: str = "alpha beta gamma") -> int:
    return log.append(kind="user_message", content=query, meta={"role": "user"})


def _v2_selection(
    log: EventLog,
    *,
    turn_id: int,
    selected: list,
    extra: dict | None = None,
) -> int:
    payload = {
        "record_version": 2,
        "turn_id": turn_id,
        "selected": selected,
        "vector_embedding_uses": [],
    }
    if extra:
        payload.update(extra)
    return log.append(
        kind="retrieval_selection",
        content=json.dumps(payload, sort_keys=True, separators=(",", ":")),
        meta={"source": "test"},
    )


def _diagnostics(log: EventLog) -> list[dict]:
    return [
        e for e in log.read_all() if e.get("kind") == VECTOR_OVERLAP_DIAGNOSTIC_KIND
    ]


def _diag_content(event: dict) -> dict:
    return json.loads(event.get("content") or "{}")


# --- T1–T5 eligibility (SQL + helper) ---


def test_t1_integer_record_version_2_is_eligible():
    log = EventLog(":memory:")
    qid = _seed_query(log)
    sid = _v2_selection(log, turn_id=qid + 1000, selected=[qid])
    rows = log.list_undiagnosed_v2_retrieval_selections(limit=5)
    assert [r["id"] for r in rows] == [sid]
    assert EventLog.is_strict_v2_retrieval_selection_content(log.get(sid)["content"])


def test_t2_real_record_version_2_0_ineligible():
    log = EventLog(":memory:")
    _seed_query(log)
    # Build JSON with a real 2.0 without Python json collapsing it.
    content = '{"record_version":2.0,"turn_id":1,"selected":[]}'
    sid = log.append(
        kind="retrieval_selection", content=content, meta={"source": "test"}
    )
    assert log.list_undiagnosed_v2_retrieval_selections(limit=5) == []
    assert not EventLog.is_strict_v2_retrieval_selection_content(content)

    payload = AutonomyKernel.build_vector_overlap_diagnostic_payload(
        target_selection_id=sid,
        evaluation={
            "outcome": "inconclusive",
            "reason_code": "MALFORMED_SELECTION",
            "evaluated": 0,
            "turn_id": None,
            "selected_count": 0,
            "top_ids": [],
        },
        model="hash64",
        dims=64,
    )
    event_id, created = log.append_vector_overlap_diagnostic(
        content=payload[0], meta=payload[1]
    )
    assert event_id is None and created is False
    assert _diagnostics(log) == []


def test_t3_string_record_version_2_ineligible():
    log = EventLog(":memory:")
    content = json.dumps({"record_version": "2", "turn_id": 1, "selected": []})
    sid = log.append(
        kind="retrieval_selection", content=content, meta={"source": "test"}
    )
    assert log.list_undiagnosed_v2_retrieval_selections(limit=5) == []
    assert not EventLog.is_strict_v2_retrieval_selection_content(content)
    payload = AutonomyKernel.build_vector_overlap_diagnostic_payload(
        target_selection_id=sid,
        evaluation={
            "outcome": "inconclusive",
            "reason_code": "MALFORMED_SELECTION",
            "evaluated": 0,
            "turn_id": None,
            "selected_count": 0,
            "top_ids": [],
        },
        model="hash64",
        dims=64,
    )
    assert log.append_vector_overlap_diagnostic(
        content=payload[0], meta=payload[1]
    ) == (
        None,
        False,
    )


def test_t4_boolean_record_version_ineligible():
    log = EventLog(":memory:")
    content = json.dumps({"record_version": True, "turn_id": 1, "selected": []})
    sid = log.append(
        kind="retrieval_selection", content=content, meta={"source": "test"}
    )
    assert log.list_undiagnosed_v2_retrieval_selections(limit=5) == []
    assert not EventLog.is_strict_v2_retrieval_selection_content(content)
    payload = AutonomyKernel.build_vector_overlap_diagnostic_payload(
        target_selection_id=sid,
        evaluation={
            "outcome": "inconclusive",
            "reason_code": "MALFORMED_SELECTION",
            "evaluated": 0,
            "turn_id": None,
            "selected_count": 0,
            "top_ids": [],
        },
        model="hash64",
        dims=64,
    )
    assert log.append_vector_overlap_diagnostic(
        content=payload[0], meta=payload[1]
    ) == (
        None,
        False,
    )


def test_t5_malformed_json_does_not_raise_and_is_ineligible():
    log = EventLog(":memory:")
    sid = log.append(
        kind="retrieval_selection",
        content="{not valid json",
        meta={"source": "test"},
    )
    # Must not raise.
    rows = log.list_undiagnosed_v2_retrieval_selections(limit=5)
    assert rows == []
    assert not EventLog.is_strict_v2_retrieval_selection_content("{not valid json")
    payload = AutonomyKernel.build_vector_overlap_diagnostic_payload(
        target_selection_id=sid,
        evaluation={
            "outcome": "inconclusive",
            "reason_code": "MALFORMED_SELECTION",
            "evaluated": 0,
            "turn_id": None,
            "selected_count": 0,
            "top_ids": [],
        },
        model="hash64",
        dims=64,
    )
    assert log.append_vector_overlap_diagnostic(
        content=payload[0], meta=payload[1]
    ) == (
        None,
        False,
    )


# --- Outcomes, uniqueness, routing, isolation ---


def test_overlap_observed_writes_diagnostic_not_reflection():
    log = EventLog(":memory:")
    qid = _seed_query(log)
    sid = _v2_selection(log, turn_id=qid + 1000, selected=[qid])

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    diags = _diagnostics(log)
    assert len(diags) == 1
    body = _diag_content(diags[0])
    assert body["outcome"] == "overlap_observed"
    assert body["reason_code"] == "OVERLAP"
    assert body["target_selection_id"] == sid
    assert body["evaluated"] == 1
    assert diags[0]["meta"]["about_event"] == sid
    assert diags[0]["meta"]["source"] == VECTOR_OVERLAP_DIAGNOSTIC_SOURCE
    assert diags[0]["meta"]["diagnostic"] == VECTOR_OVERLAP_DIAGNOSTIC_PROTOCOL
    assert not any(e.get("kind") == "reflection" for e in log.read_all())


def test_mismatch_outcome():
    log = EventLog(":memory:")
    qid = _seed_query(log)
    _v2_selection(log, turn_id=qid + 1000, selected=[qid + 999])
    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()
    body = _diag_content(_diagnostics(log)[0])
    assert body["outcome"] == "mismatch"
    assert body["reason_code"] == "NO_OVERLAP"
    assert body["evaluated"] == 1


def test_missing_query_inconclusive():
    log = EventLog(":memory:")
    _v2_selection(log, turn_id=1, selected=[])
    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()
    body = _diag_content(_diagnostics(log)[0])
    assert body["outcome"] == "inconclusive"
    assert body["reason_code"] == "MISSING_QUERY"
    assert body["evaluated"] == 0
    assert body["top_ids"] == []


def test_malformed_inner_fields_on_v2_is_malformed_selection():
    log = EventLog(":memory:")
    _seed_query(log)
    log.append(
        kind="retrieval_selection",
        content=json.dumps(
            {"record_version": 2, "turn_id": "bad", "selected": []},
            sort_keys=True,
        ),
        meta={"source": "test"},
    )
    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()
    body = _diag_content(_diagnostics(log)[0])
    assert body["outcome"] == "inconclusive"
    assert body["reason_code"] == "MALFORMED_SELECTION"


def test_empty_scored_inconclusive(monkeypatch):
    log = EventLog(":memory:")
    qid = _seed_query(log)
    _v2_selection(log, turn_id=qid + 1000, selected=[qid])
    monkeypatch.setattr("pmm.retrieval.vector.candidate_messages", lambda *a, **kw: [])
    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()
    body = _diag_content(_diagnostics(log)[0])
    assert body["outcome"] == "inconclusive"
    assert body["reason_code"] == "EMPTY_SCORED"


def test_at_most_once_second_call_returns_same_id():
    log = EventLog(":memory:")
    qid = _seed_query(log)
    sid = _v2_selection(log, turn_id=qid + 1000, selected=[qid])
    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()
    first = _diagnostics(log)
    assert len(first) == 1
    first_id = first[0]["id"]

    kernel._verify_recent_selections()
    kernel._verify_recent_selections()
    diags = _diagnostics(log)
    assert len(diags) == 1
    assert diags[0]["id"] == first_id

    # Helper idempotence with explicit rebuild of same about_event payload.
    content, meta = AutonomyKernel.build_vector_overlap_diagnostic_payload(
        target_selection_id=sid,
        evaluation={
            "outcome": "overlap_observed",
            "reason_code": "OVERLAP",
            "evaluated": 1,
            "turn_id": qid + 1000,
            "selected_count": 1,
            "top_ids": [qid],
        },
        model="hash64",
        dims=64,
    )
    event_id, created = log.append_vector_overlap_diagnostic(content=content, meta=meta)
    assert created is False
    assert event_id == first_id


def test_generic_append_routes_through_helper():
    log = EventLog(":memory:")
    qid = _seed_query(log)
    sid = _v2_selection(log, turn_id=qid + 1000, selected=[qid])
    content, meta = AutonomyKernel.build_vector_overlap_diagnostic_payload(
        target_selection_id=sid,
        evaluation={
            "outcome": "overlap_observed",
            "reason_code": "OVERLAP",
            "evaluated": 1,
            "turn_id": qid + 1000,
            "selected_count": 1,
            "top_ids": [qid],
        },
        model="hash64",
        dims=64,
    )
    # Public append must hit specialized validation/uniqueness.
    eid1 = log.append(kind=VECTOR_OVERLAP_DIAGNOSTIC_KIND, content=content, meta=meta)
    eid2 = log.append(kind=VECTOR_OVERLAP_DIAGNOSTIC_KIND, content=content, meta=meta)
    assert eid1 == eid2
    assert len(_diagnostics(log)) == 1


def test_generic_append_rejects_legacy_target():
    log = EventLog(":memory:")
    sid = log.append(
        kind="retrieval_selection",
        content=json.dumps({"turn_id": 1, "selected": []}),
        meta={"source": "test"},
    )
    content, meta = AutonomyKernel.build_vector_overlap_diagnostic_payload(
        target_selection_id=sid,
        evaluation={
            "outcome": "inconclusive",
            "reason_code": "MALFORMED_SELECTION",
            "evaluated": 0,
            "turn_id": None,
            "selected_count": 0,
            "top_ids": [],
        },
        model="hash64",
        dims=64,
    )
    with pytest.raises(ValueError, match="strict record_version=2"):
        log.append(kind=VECTOR_OVERLAP_DIAGNOSTIC_KIND, content=content, meta=meta)
    assert _diagnostics(log) == []


def test_wrong_source_rejected():
    log = EventLog(":memory:")
    qid = _seed_query(log)
    sid = _v2_selection(log, turn_id=qid + 1000, selected=[qid])
    content, meta = AutonomyKernel.build_vector_overlap_diagnostic_payload(
        target_selection_id=sid,
        evaluation={
            "outcome": "overlap_observed",
            "reason_code": "OVERLAP",
            "evaluated": 1,
            "turn_id": qid + 1000,
            "selected_count": 1,
            "top_ids": [qid],
        },
        model="hash64",
        dims=64,
    )
    meta["source"] = "not_autonomy"
    with pytest.raises(ValueError, match="source"):
        log.append_vector_overlap_diagnostic(content=content, meta=meta)


def test_type_isolation_from_rsm_intents_and_memegraph():
    log = EventLog(":memory:")
    qid = _seed_query(log)
    _v2_selection(log, turn_id=qid + 1000, selected=[qid])
    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    rsm = RecursiveSelfModel()
    for e in log.read_all():
        rsm.observe(e)
    # Diagnostic must not land in reflection_intents.
    assert rsm.reflection_intents == []

    mg = MemeGraph(log)
    mg.rebuild([e for e in log.read_all() if e.get("kind") in MemeGraph.TRACKED_KINDS])
    diag_ids = {e["id"] for e in _diagnostics(log)}
    assert diag_ids
    for did in diag_ids:
        assert not mg.graph.has_node(did)


def test_batch_processes_oldest_first_limited():
    log = EventLog(":memory:")
    qid = _seed_query(log)
    ids = []
    for i in range(7):
        ids.append(
            _v2_selection(
                log,
                turn_id=qid + 1000 + i,
                selected=[qid],
            )
        )
    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections(N=5)
    diags = _diagnostics(log)
    assert len(diags) == 5
    about = [d["meta"]["about_event"] for d in diags]
    assert about == ids[:5]

    kernel._verify_recent_selections(N=5)
    diags = _diagnostics(log)
    assert len(diags) == 7
    about = sorted(d["meta"]["about_event"] for d in diags)
    assert about == ids


def test_diagnostic_embedding_records_latest_config_params():
    log = EventLog(":memory:")
    log.append(
        kind="config",
        content=json.dumps(
            {"type": "retrieval", "model": "hash64", "dims": 32},
            sort_keys=True,
        ),
        meta={"source": "test"},
    )
    qid = _seed_query(log)
    _v2_selection(log, turn_id=qid + 1000, selected=[qid])
    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()
    body = _diag_content(_diagnostics(log)[0])
    assert body["diagnostic_embedding"] == {"model": "hash64", "dims": 32}


def test_legacy_selection_not_diagnosed_by_scheduler():
    log = EventLog(":memory:")
    qid = _seed_query(log)
    log.append(
        kind="retrieval_selection",
        content=json.dumps({"turn_id": qid + 1000, "selected": [qid]}),
        meta={"source": "test"},
    )
    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()
    assert _diagnostics(log) == []
    assert not any(e.get("kind") == "reflection" for e in log.read_all())


def _authorized_payload(
    sid: int,
    *,
    outcome: str,
    reason_code: str,
    evaluated: int,
    top_ids: list,
    turn_id: int | None = 1,
) -> tuple[str, dict]:
    return AutonomyKernel.build_vector_overlap_diagnostic_payload(
        target_selection_id=sid,
        evaluation={
            "outcome": outcome,
            "reason_code": reason_code,
            "evaluated": evaluated,
            "turn_id": turn_id,
            "selected_count": len(top_ids) if evaluated else 0,
            "top_ids": top_ids,
        },
        model="hash64",
        dims=64,
    )


@pytest.mark.parametrize(
    "outcome,reason_code,evaluated,top_ids",
    [
        ("overlap_observed", "NO_OVERLAP", 0, []),
        ("overlap_observed", "OVERLAP", 0, []),
        ("mismatch", "OVERLAP", 1, [1]),
        ("inconclusive", "OVERLAP", 0, []),
        ("overlap_observed", "NO_OVERLAP", 1, [1]),
        ("mismatch", "NO_OVERLAP", 0, []),
        ("inconclusive", "MISSING_QUERY", 1, [1]),
        ("overlap_observed", "EMPTY_SCORED", 1, [1]),
    ],
)
def test_contradictory_combinations_rejected_by_helper_and_generic_append(
    outcome, reason_code, evaluated, top_ids
):
    log = EventLog(":memory:")
    qid = _seed_query(log)
    sid = _v2_selection(log, turn_id=qid + 1000, selected=[qid])
    content, meta = _authorized_payload(
        sid,
        outcome=outcome,
        reason_code=reason_code,
        evaluated=evaluated,
        top_ids=top_ids,
        turn_id=qid + 1000 if evaluated else None,
    )
    with pytest.raises(ValueError, match="unauthorized"):
        log.append_vector_overlap_diagnostic(content=content, meta=meta)
    with pytest.raises(ValueError, match="unauthorized"):
        log.append(kind=VECTOR_OVERLAP_DIAGNOSTIC_KIND, content=content, meta=meta)
    assert _diagnostics(log) == []


def test_evaluated_0_with_nonempty_top_ids_rejected():
    log = EventLog(":memory:")
    qid = _seed_query(log)
    sid = _v2_selection(log, turn_id=qid + 1000, selected=[qid])
    content, meta = _authorized_payload(
        sid,
        outcome="inconclusive",
        reason_code="MISSING_QUERY",
        evaluated=0,
        top_ids=[qid],
        turn_id=None,
    )
    with pytest.raises(ValueError, match="top_ids must be empty"):
        log.append_vector_overlap_diagnostic(content=content, meta=meta)
    with pytest.raises(ValueError, match="top_ids must be empty"):
        log.append(kind=VECTOR_OVERLAP_DIAGNOSTIC_KIND, content=content, meta=meta)


def test_evaluated_1_with_empty_top_ids_rejected():
    log = EventLog(":memory:")
    qid = _seed_query(log)
    sid = _v2_selection(log, turn_id=qid + 1000, selected=[qid])
    content, meta = _authorized_payload(
        sid,
        outcome="overlap_observed",
        reason_code="OVERLAP",
        evaluated=1,
        top_ids=[],
        turn_id=qid + 1000,
    )
    with pytest.raises(ValueError, match="top_ids must be non-empty"):
        log.append_vector_overlap_diagnostic(content=content, meta=meta)


def test_pure_evaluator_exception_becomes_durable_evaluator_error(monkeypatch):
    log = EventLog(":memory:")
    qid = _seed_query(log)
    sid = _v2_selection(log, turn_id=qid + 1000, selected=[qid])

    def _boom(*_a, **_k):
        raise RuntimeError("pure evaluate exploded")

    monkeypatch.setattr(
        AutonomyKernel,
        "evaluate_vector_overlap_for_selection",
        staticmethod(_boom),
    )
    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    diags = _diagnostics(log)
    assert len(diags) == 1
    body = _diag_content(diags[0])
    assert body["outcome"] == "inconclusive"
    assert body["reason_code"] == "EVALUATOR_ERROR"
    assert body["evaluated"] == 0
    assert body["top_ids"] == []
    assert body["target_selection_id"] == sid
    assert diags[0]["meta"]["about_event"] == sid


def test_append_validation_failure_propagates_not_evaluator_error():
    """Writer-path validation errors must not be swallowed as EVALUATOR_ERROR."""

    log = EventLog(":memory:")
    qid = _seed_query(log)
    sid = _v2_selection(log, turn_id=qid + 1000, selected=[qid])
    content, meta = _authorized_payload(
        sid,
        outcome="overlap_observed",
        reason_code="NO_OVERLAP",
        evaluated=0,
        top_ids=[],
    )
    with pytest.raises(ValueError, match="unauthorized"):
        log.append_vector_overlap_diagnostic(content=content, meta=meta)
    assert _diagnostics(log) == []


def test_ownership_failure_on_append_propagates(monkeypatch):
    log = EventLog(":memory:")
    qid = _seed_query(log)
    sid = _v2_selection(log, turn_id=qid + 1000, selected=[qid])
    content, meta = _authorized_payload(
        sid,
        outcome="overlap_observed",
        reason_code="OVERLAP",
        evaluated=1,
        top_ids=[qid],
        turn_id=qid + 1000,
    )

    def _deny(*_a, **_k):
        raise PermissionError("writer authority denied")

    monkeypatch.setattr(log.writer_session, "assert_authority_in_transaction", _deny)
    with pytest.raises(PermissionError, match="writer authority denied"):
        log.append_vector_overlap_diagnostic(content=content, meta=meta)
    assert _diagnostics(log) == []


def test_scheduler_append_failure_propagates_not_caught_as_evaluator(monkeypatch):
    log = EventLog(":memory:")
    qid = _seed_query(log)
    _v2_selection(log, turn_id=qid + 1000, selected=[qid])

    def _boom_append(*_a, **_k):
        raise RuntimeError("transaction/append failed")

    monkeypatch.setattr(log, "append_vector_overlap_diagnostic", _boom_append)
    kernel = AutonomyKernel(log)
    with pytest.raises(RuntimeError, match="transaction/append failed"):
        kernel._verify_recent_selections()
    assert _diagnostics(log) == []
