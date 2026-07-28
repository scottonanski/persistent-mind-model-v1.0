# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""R17 phase 1 — vector-parameter provenance fidelity.

Guarantee under test:

    For every version-2 retrieval-selection record, ``vector_embedding_uses``
    exhaustively identifies the vector stages that ran and truthfully records
    the embedding model and dimensions passed to each invocation.

These tests cover the pipeline channel and the recorder's use of it. They do
not test the retrieval verifier, hybrid reproducibility, or whether retrieval
configuration should drive embedding parameters.
"""

import json

from pmm.core.concept_graph import ConceptGraph
from pmm.core.event_log import EventLog
from pmm.core.meme_graph import MemeGraph
from pmm.retrieval import pipeline as pipeline_mod
from pmm.retrieval.pipeline import (
    VECTOR_EMBEDDING_DIMS,
    VECTOR_EMBEDDING_MODEL,
    RetrievalConfig,
    run_retrieval_pipeline,
)


def _seeded_log():
    log = EventLog(":memory:")
    mg = MemeGraph(log)
    cg = ConceptGraph(log)
    log.append(kind="user_message", content="alpha beta", meta={"role": "user"})
    log.append(
        kind="assistant_message", content="beta gamma", meta={"role": "assistant"}
    )
    log.append(kind="lifetime_memory", content="alpha summary", meta={})
    mg.rebuild(log.read_all())
    cg.rebuild(log.read_all())
    return log, mg, cg


def _run(log, mg, cg, config, query_text="alpha"):
    return run_retrieval_pipeline(
        query_text=query_text,
        eventlog=log,
        concept_graph=cg,
        meme_graph=mg,
        config=config,
    )


# --- pipeline: entries exist only when a call actually runs -----------------


def _both_stages_log():
    """Ledger where thread refinement AND summary search both have work.

    ``_refine_with_vector`` runs only over a non-empty candidate set, so a
    concept must be bound to an event and seeded; the summary stage needs
    ``lifetime_memory`` events to scan.
    """
    log = EventLog(":memory:")
    mg = MemeGraph(log)
    cg = ConceptGraph(log)

    log.append(
        kind="concept_define",
        content=json.dumps(
            {
                "token": "topic.alpha",
                "concept_kind": "topic",
                "definition": "alpha",
                "attributes": {},
                "version": "1.0",
            }
        ),
        meta={},
    )
    bound = log.append(kind="user_message", content="alpha beta", meta={"role": "user"})
    log.append(
        kind="concept_bind_event",
        content=json.dumps(
            {"event_id": bound, "tokens": ["topic.alpha"], "relation": "relates_to"}
        ),
        meta={},
    )
    log.append(kind="lifetime_memory", content="alpha beta summary", meta={})
    log.append(kind="lifetime_memory", content="gamma delta summary", meta={})

    mg.rebuild(log.read_all())
    cg.rebuild(log.read_all())
    return log, mg, cg


def test_both_stages_recorded_and_match_their_calls():
    """Exactly two entries, one per invocation, each matching its own call."""
    log, mg, cg = _both_stages_log()
    calls = []
    real = pipeline_mod.select_by_vector

    def spy(*args, **kwargs):
        calls.append({"model": kwargs.get("model"), "dims": kwargs.get("dims")})
        return real(*args, **kwargs)

    pipeline_mod.select_by_vector = spy
    try:
        res = _run(
            log,
            mg,
            cg,
            RetrievalConfig(always_include_concepts=["topic.alpha"]),
            query_text="alpha",
        )
    finally:
        pipeline_mod.select_by_vector = real

    stages = [u["stage"] for u in res.vector_embedding_uses]
    assert stages == ["thread_refinement", "summary_search"], stages
    assert len(calls) == len(res.vector_embedding_uses) == 2

    # Every captured call's parameters equal its corresponding entry's.
    for call, use in zip(calls, res.vector_embedding_uses):
        assert use["model"] == call["model"]
        assert use["dims"] == call["dims"]
        assert use["model"] == VECTOR_EMBEDDING_MODEL
        assert use["dims"] == VECTOR_EMBEDDING_DIMS


def test_uses_recorded_for_each_invocation_that_runs():
    log, mg, cg = _seeded_log()
    res = _run(log, mg, cg, RetrievalConfig())

    stages = [u["stage"] for u in res.vector_embedding_uses]
    assert stages, "expected at least one vector invocation for this fixture"
    assert set(stages) <= {"thread_refinement", "summary_search"}
    for use in res.vector_embedding_uses:
        assert use["model"] == VECTOR_EMBEDDING_MODEL
        assert use["dims"] == VECTOR_EMBEDDING_DIMS


def test_no_uses_when_vector_search_disabled():
    log, mg, cg = _seeded_log()
    res = _run(log, mg, cg, RetrievalConfig(enable_vector_search=False))
    assert res.vector_embedding_uses == []


def test_no_uses_when_query_text_empty():
    log, mg, cg = _seeded_log()
    res = _run(log, mg, cg, RetrievalConfig(), query_text="")
    assert res.vector_embedding_uses == []


def test_summary_stage_absent_when_summary_search_disabled():
    log, mg, cg = _seeded_log()
    res = _run(log, mg, cg, RetrievalConfig(enable_summary_vector_search=False))
    stages = [u["stage"] for u in res.vector_embedding_uses]
    assert "summary_search" not in stages


def test_recorded_values_track_the_call_not_a_separate_constant():
    """The record must follow what select_by_vector is actually passed.

    Patching the module constant changes both the call and the record together;
    a record built from an independent literal would fail this.
    """
    log, mg, cg = _seeded_log()
    seen = {}
    real = pipeline_mod.select_by_vector

    def spy(*args, **kwargs):
        seen.setdefault("model", kwargs.get("model"))
        seen.setdefault("dims", kwargs.get("dims"))
        return real(*args, **kwargs)

    pipeline_mod.select_by_vector = spy
    pipeline_mod.VECTOR_EMBEDDING_MODEL = "hash64_tfidf"
    pipeline_mod.VECTOR_EMBEDDING_DIMS = 8
    try:
        res = _run(log, mg, cg, RetrievalConfig())
    finally:
        pipeline_mod.select_by_vector = real
        pipeline_mod.VECTOR_EMBEDDING_MODEL = VECTOR_EMBEDDING_MODEL
        pipeline_mod.VECTOR_EMBEDDING_DIMS = VECTOR_EMBEDDING_DIMS

    assert seen["model"] == "hash64_tfidf"
    assert seen["dims"] == 8
    for use in res.vector_embedding_uses:
        assert use["model"] == seen["model"]
        assert use["dims"] == seen["dims"]


def test_parameters_are_passed_explicitly_not_left_to_defaults():
    log, mg, cg = _seeded_log()
    calls = []
    real = pipeline_mod.select_by_vector

    def spy(*args, **kwargs):
        calls.append(kwargs)
        return real(*args, **kwargs)

    pipeline_mod.select_by_vector = spy
    try:
        _run(log, mg, cg, RetrievalConfig())
    finally:
        pipeline_mod.select_by_vector = real

    assert calls, "expected at least one vector invocation"
    for kwargs in calls:
        assert "model" in kwargs and "dims" in kwargs


# --- recorder: version 2 record shape and digest omission ------------------


def _selection_records(log):
    return [e for e in log.read_all() if e.get("kind") == "retrieval_selection"]


def _run_turn(with_summaries=False):
    """Drive the real recorder through RuntimeLoop.run_turn.

    ``RuntimeLoop`` constructs its own ``RetrievalConfig`` per turn, so vector
    invocation is steered by ledger contents rather than injected config. A bare
    ledger seeds no concepts and holds no summaries, so no vector call runs;
    seeding ``lifetime_memory`` events makes the summary stage execute.
    """
    from pmm.adapters.dummy_adapter import DummyAdapter
    from pmm.runtime.loop import RuntimeLoop

    log = EventLog(":memory:")
    if with_summaries:
        log.append(kind="lifetime_memory", content="alpha beta summary", meta={})
        log.append(kind="lifetime_memory", content="gamma delta summary", meta={})
    loop = RuntimeLoop(eventlog=log, adapter=DummyAdapter(), autonomy=False)
    loop.run_turn("alpha beta")
    return log


def test_version_2_record_with_uses_carries_digest_and_true_parameters():
    log = _run_turn(with_summaries=True)
    records = _selection_records(log)
    assert records, "expected a retrieval_selection record"
    rec = records[-1]
    data = json.loads(rec["content"])

    assert data["record_version"] == 2
    uses = data["vector_embedding_uses"]
    assert uses, "expected at least one vector invocation on this turn"
    for use in uses:
        assert use["model"] == VECTOR_EMBEDDING_MODEL
        assert use["dims"] == VECTOR_EMBEDDING_DIMS

    # Top-level parameters describe what ran, not what configuration names.
    assert data["model"] == VECTOR_EMBEDDING_MODEL
    assert data["dims"] == VECTOR_EMBEDDING_DIMS
    assert (rec.get("meta") or {}).get("digest")


def test_version_2_record_without_uses_omits_digest_and_parameters():
    # A first turn on a bare ledger runs no vector stage at all: nothing is
    # seeded to refine and no summaries exist to search.
    log = _run_turn(with_summaries=False)
    records = _selection_records(log)
    assert records, "expected a retrieval_selection record even with no vector stage"
    rec = records[-1]
    data = json.loads(rec["content"])

    assert data["record_version"] == 2
    assert data["vector_embedding_uses"] == []
    # No invented parameters and no digest built from them.
    assert "model" not in data
    assert "dims" not in data
    assert "digest" not in (rec.get("meta") or {})


def test_recorder_ignores_mirror_configuration_for_parameters():
    """A divergent configured model must not reach the record.

    This is the original R17 finding-1 defect expressed as a test.
    """
    from pmm.adapters.dummy_adapter import DummyAdapter
    from pmm.runtime.loop import RuntimeLoop

    log = EventLog(":memory:")
    log.append(kind="lifetime_memory", content="alpha beta summary", meta={})
    log.append(kind="lifetime_memory", content="gamma delta summary", meta={})
    loop = RuntimeLoop(eventlog=log, adapter=DummyAdapter(), autonomy=False)
    loop.mirror.current_retrieval_config = {
        "type": "retrieval",
        "strategy": "hybrid",
        "model": "hash64_tfidf",
        "dims": 8,
    }
    loop.run_turn("alpha beta")

    records = _selection_records(log)
    assert records
    data = json.loads(records[-1]["content"])
    uses = data["vector_embedding_uses"]
    assert uses, "fixture must produce a vector invocation or the test is vacuous"
    for use in uses:
        assert use["model"] == VECTOR_EMBEDDING_MODEL
        assert use["dims"] == VECTOR_EMBEDDING_DIMS
    assert data["model"] == VECTOR_EMBEDDING_MODEL
    assert data["dims"] == VECTOR_EMBEDDING_DIMS
