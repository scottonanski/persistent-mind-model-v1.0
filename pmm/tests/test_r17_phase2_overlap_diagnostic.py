# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""R17 phase 2 weak-overlap outcome semantics (preserved under Phase 3).

Phase 3 records per-selection ``vector_overlap_diagnostic`` events instead of
aggregate reflections. Outcome rules for an *evaluated* eligible selection
remain: mismatch / inconclusive / overlap_observed with the Phase 2 weak
top-k intersection test. These tests require strict-v2 selection records.
"""

from __future__ import annotations

import json

from pmm.core.event_log import VECTOR_OVERLAP_DIAGNOSTIC_KIND, EventLog
from pmm.runtime.autonomy_kernel import AutonomyKernel


def _last_diagnostic(log: EventLog) -> dict:
    events = log.read_all()
    for e in reversed(events):
        if e.get("kind") == VECTOR_OVERLAP_DIAGNOSTIC_KIND:
            return json.loads(e.get("content") or "{}")
    raise AssertionError("no vector_overlap_diagnostic was appended")


def _seed_query_and_candidates(log: EventLog, query: str) -> int:
    return log.append(kind="user_message", content=query, meta={"role": "user"})


def _append_v2_selection(log: EventLog, *, content_obj: dict) -> int:
    payload = dict(content_obj)
    payload["record_version"] = 2
    return log.append(
        kind="retrieval_selection",
        content=json.dumps(payload, sort_keys=True, separators=(",", ":")),
        meta={"source": "test"},
    )


def test_valid_overlap_yields_overlap_observed():
    log = EventLog(":memory:")
    qid = _seed_query_and_candidates(log, "alpha beta gamma")
    _append_v2_selection(log, content_obj={"turn_id": qid + 1000, "selected": [qid]})

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_diagnostic(log)
    assert outcome["outcome"] == "overlap_observed"
    assert outcome["reason_code"] == "OVERLAP"
    assert outcome["evaluated"] == 1


def test_mismatch_when_selection_excludes_top_match():
    log = EventLog(":memory:")
    qid = _seed_query_and_candidates(log, "alpha beta gamma")
    _append_v2_selection(
        log, content_obj={"turn_id": qid + 1000, "selected": [qid + 999]}
    )

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_diagnostic(log)
    assert outcome["outcome"] == "mismatch"
    assert outcome["reason_code"] == "NO_OVERLAP"
    assert outcome["evaluated"] == 1


def test_malformed_turn_id_is_inconclusive_not_raise():
    log = EventLog(":memory:")
    _seed_query_and_candidates(log, "alpha beta gamma")
    _append_v2_selection(log, content_obj={"turn_id": "not-an-int", "selected": []})

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_diagnostic(log)
    assert outcome["outcome"] == "inconclusive"
    assert outcome["reason_code"] == "MALFORMED_SELECTION"
    assert outcome["evaluated"] == 0


def test_missing_query_is_inconclusive():
    log = EventLog(":memory:")
    _append_v2_selection(log, content_obj={"turn_id": 1, "selected": []})

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_diagnostic(log)
    assert outcome["outcome"] == "inconclusive"
    assert outcome["reason_code"] == "MISSING_QUERY"
    assert outcome["evaluated"] == 0


def test_empty_scoring_is_inconclusive(monkeypatch):
    log = EventLog(":memory:")
    qid = _seed_query_and_candidates(log, "alpha beta gamma")
    _append_v2_selection(log, content_obj={"turn_id": qid + 1000, "selected": [qid]})

    monkeypatch.setattr("pmm.retrieval.vector.candidate_messages", lambda *a, **kw: [])

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_diagnostic(log)
    assert outcome["outcome"] == "inconclusive"
    assert outcome["reason_code"] == "EMPTY_SCORED"
    assert outcome["evaluated"] == 0


def test_fractional_turn_id_is_inconclusive():
    log = EventLog(":memory:")
    qid = _seed_query_and_candidates(log, "alpha beta gamma")
    _append_v2_selection(
        log, content_obj={"turn_id": float(qid + 1000), "selected": [qid]}
    )

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_diagnostic(log)
    assert outcome["outcome"] == "inconclusive"
    assert outcome["reason_code"] == "MALFORMED_SELECTION"


def test_boolean_turn_id_is_inconclusive():
    log = EventLog(":memory:")
    _seed_query_and_candidates(log, "alpha beta gamma")
    _append_v2_selection(log, content_obj={"turn_id": True, "selected": []})

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_diagnostic(log)
    assert outcome["outcome"] == "inconclusive"
    assert outcome["reason_code"] == "MALFORMED_SELECTION"


def test_non_list_selected_is_inconclusive():
    log = EventLog(":memory:")
    qid = _seed_query_and_candidates(log, "alpha beta gamma")
    _append_v2_selection(
        log, content_obj={"turn_id": qid + 1000, "selected": "not-a-list"}
    )

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_diagnostic(log)
    assert outcome["outcome"] == "inconclusive"
    assert outcome["reason_code"] == "MALFORMED_SELECTION"


def test_boolean_ids_in_selected_is_inconclusive():
    log = EventLog(":memory:")
    qid = _seed_query_and_candidates(log, "alpha beta gamma")
    _append_v2_selection(
        log, content_obj={"turn_id": qid + 1000, "selected": [True, qid]}
    )

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_diagnostic(log)
    assert outcome["outcome"] == "inconclusive"
    assert outcome["reason_code"] == "MALFORMED_SELECTION"


def test_numeric_string_turn_id_is_inconclusive():
    log = EventLog(":memory:")
    qid = _seed_query_and_candidates(log, "alpha beta gamma")
    _append_v2_selection(
        log, content_obj={"turn_id": str(qid + 1000), "selected": [qid]}
    )

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_diagnostic(log)
    assert outcome["outcome"] == "inconclusive"
    assert outcome["reason_code"] == "MALFORMED_SELECTION"


def test_malformed_outer_json_is_not_eligible_under_v2_contraction():
    """Proposed coverage contraction: invalid JSON is skipped, not diagnosed."""

    log = EventLog(":memory:")
    _seed_query_and_candidates(log, "alpha beta gamma")
    log.append(
        kind="retrieval_selection",
        content="{not valid json",
        meta={"source": "test"},
    )

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    assert not any(
        e.get("kind") == VECTOR_OVERLAP_DIAGNOSTIC_KIND for e in log.read_all()
    )
    assert not any(e.get("kind") == "reflection" for e in log.read_all())
