# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""R17 phase 2 — vector overlap diagnostic outcome semantics.

Guarantee under test:

    AutonomyKernel._verify_recent_selections must never emit a positive
    result unless every targeted retrieval-selection record was successfully
    evaluated, at least one evaluation occurred, and every evaluated record
    had the required vector overlap.

These tests exercise the diagnostic in isolation. They do not test complete
hybrid-retrieval reproduction, exactly-once scheduling, attribution, or
configuration-driven retrieval.
"""

from __future__ import annotations

import json

from pmm.core.event_log import EventLog
from pmm.runtime.autonomy_kernel import AutonomyKernel


def _last_reflection(log: EventLog) -> dict:
    events = log.read_all()
    for e in reversed(events):
        if e.get("kind") == "reflection":
            return json.loads(e.get("content") or "{}")
    raise AssertionError("no reflection event was appended")


def _seed_query_and_candidates(log: EventLog, query: str) -> int:
    """Append a user_message usable as both query and vector candidate.

    Returns its event id. A retrieval_selection with turn_id greater than
    this id will find it as the "last user_message before turn" query, and
    since the deterministic embedder maps identical text to an identical
    vector, this event is also the top vector match for that query.
    """
    return log.append(kind="user_message", content=query, meta={"role": "user"})


def _append_selection(log: EventLog, *, content: str) -> int:
    return log.append(
        kind="retrieval_selection", content=content, meta={"source": "test"}
    )


def test_valid_overlap_yields_overlap_observed():
    log = EventLog(":memory:")
    qid = _seed_query_and_candidates(log, "alpha beta gamma")
    sel_content = json.dumps({"turn_id": qid + 1000, "selected": [qid]})
    _append_selection(log, content=sel_content)

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_reflection(log)
    assert outcome["outcome"] == "overlap_observed"
    assert "vector overlap diagnostic: overlap_observed" in outcome["intent"]
    assert "targeted=1" in outcome["intent"]
    assert "evaluated=1" in outcome["intent"]


def test_mismatch_when_selection_excludes_top_match():
    log = EventLog(":memory:")
    qid = _seed_query_and_candidates(log, "alpha beta gamma")
    # Selected id does not correspond to any real candidate, so it cannot be
    # among the top vector matches.
    sel_content = json.dumps({"turn_id": qid + 1000, "selected": [qid + 999]})
    _append_selection(log, content=sel_content)

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_reflection(log)
    assert outcome["outcome"] == "mismatch"
    assert "vector overlap diagnostic: mismatch" in outcome["intent"]
    assert "targeted=1" in outcome["intent"]
    assert "evaluated=1" in outcome["intent"]


def test_malformed_outer_json_is_inconclusive_not_success_or_raise():
    log = EventLog(":memory:")
    _seed_query_and_candidates(log, "alpha beta gamma")
    _append_selection(log, content="{not valid json")

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_reflection(log)
    assert outcome["outcome"] == "inconclusive"
    assert "targeted=1" in outcome["intent"]
    assert "evaluated=0" in outcome["intent"]


def test_malformed_turn_id_is_inconclusive_not_raise():
    log = EventLog(":memory:")
    _seed_query_and_candidates(log, "alpha beta gamma")
    sel_content = json.dumps({"turn_id": "not-an-int", "selected": []})
    _append_selection(log, content=sel_content)

    kernel = AutonomyKernel(log)
    # Must not raise.
    kernel._verify_recent_selections()

    outcome = _last_reflection(log)
    assert outcome["outcome"] == "inconclusive"
    assert "targeted=1" in outcome["intent"]
    assert "evaluated=0" in outcome["intent"]


def test_missing_query_is_inconclusive():
    log = EventLog(":memory:")
    # No user_message precedes turn_id at all, so no query can be found.
    sel_content = json.dumps({"turn_id": 1, "selected": []})
    sel_id = _append_selection(log, content=sel_content)
    assert sel_id >= 1

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_reflection(log)
    assert outcome["outcome"] == "inconclusive"
    assert "targeted=1" in outcome["intent"]
    assert "evaluated=0" in outcome["intent"]


def test_empty_scoring_is_inconclusive(monkeypatch):
    log = EventLog(":memory:")
    qid = _seed_query_and_candidates(log, "alpha beta gamma")
    sel_content = json.dumps({"turn_id": qid + 1000, "selected": [qid]})
    _append_selection(log, content=sel_content)

    # Force the candidate set to be empty so scoring cannot establish
    # inclusion either way, exercising the empty-scored path directly.
    monkeypatch.setattr("pmm.retrieval.vector.candidate_messages", lambda *a, **kw: [])

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_reflection(log)
    assert outcome["outcome"] == "inconclusive"
    assert "targeted=1" in outcome["intent"]
    assert "evaluated=0" in outcome["intent"]


def test_mixed_overlap_plus_inconclusive_is_inconclusive():
    log = EventLog(":memory:")
    qid = _seed_query_and_candidates(log, "alpha beta gamma")
    good = json.dumps({"turn_id": qid + 1000, "selected": [qid]})
    _append_selection(log, content=good)
    _append_selection(log, content="{not valid json")

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_reflection(log)
    # One evaluated selection had overlap, but the other targeted selection
    # was never evaluated, so the result cannot be positive.
    assert outcome["outcome"] == "inconclusive"
    assert "targeted=2" in outcome["intent"]
    assert "evaluated=1" in outcome["intent"]


def test_mixed_mismatch_plus_inconclusive_is_mismatch():
    log = EventLog(":memory:")
    qid = _seed_query_and_candidates(log, "alpha beta gamma")
    bad = json.dumps({"turn_id": qid + 1000, "selected": [qid + 999]})
    _append_selection(log, content=bad)
    _append_selection(log, content="{not valid json")

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_reflection(log)
    # Precedence: mismatch outranks inconclusive even though another
    # targeted selection was also unevaluated.
    assert outcome["outcome"] == "mismatch"
    assert "targeted=2" in outcome["intent"]
    assert "evaluated=1" in outcome["intent"]


def test_zero_evaluations_never_produces_a_positive_result():
    log = EventLog(":memory:")
    _seed_query_and_candidates(log, "alpha beta gamma")
    _append_selection(log, content="{not valid json")
    _append_selection(log, content=json.dumps({"turn_id": "bad", "selected": []}))

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_reflection(log)
    assert outcome["outcome"] != "overlap_observed"
    assert outcome["outcome"] == "inconclusive"
    assert "targeted=2" in outcome["intent"]
    assert "evaluated=0" in outcome["intent"]


def test_non_object_json_root_is_inconclusive():
    log = EventLog(":memory:")
    _seed_query_and_candidates(log, "alpha beta gamma")
    # Valid JSON, but the root is a list rather than an object.
    _append_selection(log, content="[]")

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_reflection(log)
    assert outcome["outcome"] == "inconclusive"
    assert "targeted=1" in outcome["intent"]
    assert "evaluated=0" in outcome["intent"]


def test_fractional_turn_id_is_inconclusive():
    log = EventLog(":memory:")
    qid = _seed_query_and_candidates(log, "alpha beta gamma")
    sel_content = json.dumps({"turn_id": float(qid + 1000), "selected": [qid]})
    _append_selection(log, content=sel_content)

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_reflection(log)
    assert outcome["outcome"] == "inconclusive"
    assert "targeted=1" in outcome["intent"]
    assert "evaluated=0" in outcome["intent"]


def test_boolean_turn_id_is_inconclusive():
    log = EventLog(":memory:")
    _seed_query_and_candidates(log, "alpha beta gamma")
    # bool is a subclass of int in Python; it must still be rejected.
    sel_content = json.dumps({"turn_id": True, "selected": []})
    _append_selection(log, content=sel_content)

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_reflection(log)
    assert outcome["outcome"] == "inconclusive"
    assert "targeted=1" in outcome["intent"]
    assert "evaluated=0" in outcome["intent"]


def test_non_list_selected_is_inconclusive():
    log = EventLog(":memory:")
    qid = _seed_query_and_candidates(log, "alpha beta gamma")
    sel_content = json.dumps({"turn_id": qid + 1000, "selected": "not-a-list"})
    _append_selection(log, content=sel_content)

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_reflection(log)
    assert outcome["outcome"] == "inconclusive"
    assert "targeted=1" in outcome["intent"]
    assert "evaluated=0" in outcome["intent"]


def test_boolean_ids_in_selected_is_inconclusive():
    log = EventLog(":memory:")
    qid = _seed_query_and_candidates(log, "alpha beta gamma")
    sel_content = json.dumps({"turn_id": qid + 1000, "selected": [True, qid]})
    _append_selection(log, content=sel_content)

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_reflection(log)
    assert outcome["outcome"] == "inconclusive"
    assert "targeted=1" in outcome["intent"]
    assert "evaluated=0" in outcome["intent"]


def test_numeric_string_turn_id_is_inconclusive():
    log = EventLog(":memory:")
    qid = _seed_query_and_candidates(log, "alpha beta gamma")
    # Strict identifier typing: numeric strings are not accepted policy and
    # must not be coerced via int(...).
    sel_content = json.dumps({"turn_id": str(qid + 1000), "selected": [qid]})
    _append_selection(log, content=sel_content)

    kernel = AutonomyKernel(log)
    kernel._verify_recent_selections()

    outcome = _last_reflection(log)
    assert outcome["outcome"] == "inconclusive"
    assert "targeted=1" in outcome["intent"]
    assert "evaluated=0" in outcome["intent"]
