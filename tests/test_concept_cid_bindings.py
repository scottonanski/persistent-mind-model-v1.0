import json

from pmm.core.event_log import EventLog
from pmm.core.concept_graph import ConceptGraph
from pmm.core.meme_graph import MemeGraph
from pmm.retrieval.pipeline import RetrievalConfig, run_retrieval_pipeline


def _append(eventlog: EventLog, kind: str, content: str = "", meta=None) -> int:
    return eventlog.append(kind=kind, content=content, meta=meta or {})


def test_concept_bind_thread_rebuild_and_queries():
    log = EventLog(":memory:")
    # Minimal thread: assistant -> open -> close
    _append(log, "assistant_message", "Hello", meta={"role": "assistant"})
    open_id = _append(
        log, "commitment_open", "", meta={"cid": "cid_a", "text": "Do thing"}
    )
    close_id = _append(log, "commitment_close", "", meta={"cid": "cid_a"})
    bind_payload = json.dumps(
        {"cid": "cid_a", "tokens": ["topic.test"], "relation": "relevant_to"},
        sort_keys=True,
        separators=(",", ":"),
    )
    _append(log, "concept_bind_thread", bind_payload, meta={"source": "test"})

    cg = ConceptGraph(log)
    cg.rebuild()
    mg = MemeGraph(log)
    mg.rebuild(log.read_all())

    cids = cg.resolve_cids_for_concepts(["topic.test"])
    assert "cid_a" in cids
    concepts = cg.resolve_concepts_for_cid("cid_a")
    assert "topic.test" in concepts

    # Thread slice should include the open/close events deterministically
    slice_ids = mg.get_thread_slice("cid_a", limit=5)
    assert close_id in slice_ids
    assert open_id in slice_ids


def test_retrieval_pipeline_uses_thread_bindings():
    log = EventLog(":memory:")
    _append(log, "user_message", "hi", meta={"role": "user"})
    _append(log, "assistant_message", "response", meta={"role": "assistant"})
    _append(log, "commitment_open", "", meta={"cid": "cid_b", "text": "Goal"})
    close_id = _append(log, "commitment_close", "", meta={"cid": "cid_b"})
    bind_payload = json.dumps(
        {"cid": "cid_b", "tokens": ["topic.pipeline"], "relation": "relevant_to"},
        sort_keys=True,
        separators=(",", ":"),
    )
    _append(log, "concept_bind_thread", bind_payload, meta={"source": "test"})

    cg = ConceptGraph(log)
    cg.rebuild()
    mg = MemeGraph(log)
    mg.rebuild(log.read_all())

    cfg = RetrievalConfig(
        limit_total_events=20,
        enable_vector_search=False,
        always_include_concepts=["topic.pipeline"],
    )
    result = run_retrieval_pipeline(
        query_text="pipeline check",
        eventlog=log,
        concept_graph=cg,
        meme_graph=mg,
        config=cfg,
        user_event=None,
    )

    assert "cid_b" in result.relevant_cids
    assert close_id in result.event_ids
