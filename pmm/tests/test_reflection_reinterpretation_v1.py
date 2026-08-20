from __future__ import annotations

import json

import pytest

from pmm.adapters.dummy_adapter import DummyAdapter
from pmm.core.commitment_manager import CommitmentManager
from pmm.core.commitment_outcome import (
    OUTCOME_PROTOCOL_V1,
    REINTERPRETATION_PROTOCOL_V1,
    REVIEW_PROTOCOL_V1,
    canonical_outcome_content,
    canonical_reinterpretation_content,
    canonical_review_content,
)
from pmm.core.enhancements.meta_reflection_engine import MetaReflectionEngine
from pmm.core.event_log import (
    EventLog,
    ReflectionReinterpretationRejected,
    TERMINAL_OUTCOME_PROTOCOL,
)
from pmm.core.meme_graph import MemeGraph
from pmm.core.mirror import Mirror
from pmm.meta_learning.pattern_detector import detect_learning_patterns
from pmm.runtime.identity_summary import maybe_append_summary
from pmm.runtime.loop import RuntimeLoop
from pmm.stability.stability_monitor import calculate_stability_metrics


def _managed_assistant(log: EventLog, content: str) -> int:
    producer = getattr(log, "_test_managed_runtime", None)
    if producer is None:
        producer = RuntimeLoop(eventlog=log, adapter=DummyAdapter(), autonomy=False)
        log._test_managed_runtime = producer
    user_id = log.append(
        kind="user_message",
        content="continue",
        meta={"role": "user", "turn_protocol": TERMINAL_OUTCOME_PROTOCOL},
    )
    assistant_id, created = log._append_managed_assistant_outcome(
        producer=producer,
        user_event_id=user_id,
        content=content,
        meta={"role": "assistant"},
    )
    assert created is True
    return assistant_id


def _closed_episode(log: EventLog) -> tuple[str, int, int]:
    text = "finish one exact review chain"
    opening_assistant = _managed_assistant(log, f"COMMIT: {text}")
    manager = CommitmentManager(log)
    cid, created = manager.open_commitment_status(
        text, source="assistant", origin_event_id=opening_assistant
    )
    assert created is True
    open_event_id = next(
        event["id"]
        for event in log.read_all()
        if event["kind"] == "commitment_open"
        and (event.get("meta") or {}).get("cid") == cid
    )
    closing_assistant = _managed_assistant(log, f"CLOSE: {cid}")
    close_event_id, closed = manager.close_commitment_status(
        cid, source="assistant", origin_event_id=closing_assistant
    )
    assert closed is True and close_event_id is not None
    return cid, open_event_id, close_event_id


def _authoritative_review(log: EventLog) -> tuple[str, int, int, int]:
    cid, open_event_id, close_event_id = _closed_episode(log)
    observation = "The exact work completed."
    outcome_candidate = {
        "cid": cid,
        "open_event_id": open_event_id,
        "close_event_id": close_event_id,
        "observation": observation,
        "evidence_event_ids": [close_event_id],
    }
    outcome_origin = _managed_assistant(
        log,
        "COMMITMENT_OUTCOME:"
        + json.dumps(outcome_candidate, sort_keys=True, separators=(",", ":")),
    )
    outcome_id = log.append(
        kind="outcome_observation",
        content=canonical_outcome_content(
            observation=observation, evidence_event_ids=[close_event_id]
        ),
        meta={
            "protocol": OUTCOME_PROTOCOL_V1,
            "source": "assistant",
            "cid": cid,
            "open_event_id": open_event_id,
            "close_event_id": close_event_id,
            "origin_event_id": outcome_origin,
        },
    )
    interpretation = "The result justified a bounded follow-up."
    review_candidate = {
        "cid": cid,
        "open_event_id": open_event_id,
        "outcome_event_id": outcome_id,
        "interpretation": interpretation,
    }
    review_origin = _managed_assistant(
        log,
        "COMMITMENT_REVIEW:"
        + json.dumps(review_candidate, sort_keys=True, separators=(",", ":")),
    )
    review_id = log.append(
        kind="reflection",
        content=canonical_review_content(interpretation=interpretation),
        meta={
            "protocol": REVIEW_PROTOCOL_V1,
            "source": "assistant",
            "cid": cid,
            "open_event_id": open_event_id,
            "outcome_event_id": outcome_id,
            "origin_event_id": review_origin,
        },
    )
    return cid, open_event_id, outcome_id, review_id


def _reinterpretation_attempt(
    log: EventLog,
    *,
    cid: str,
    open_event_id: int,
    outcome_event_id: int,
    review_event_id: int,
    reinterpretation: str,
) -> tuple[str, dict[str, object], int]:
    candidate = {
        "cid": cid,
        "open_event_id": open_event_id,
        "outcome_event_id": outcome_event_id,
        "review_event_id": review_event_id,
        "reinterpretation": reinterpretation,
    }
    origin_id = _managed_assistant(
        log,
        "REFLECTION_REINTERPRETATION:"
        + json.dumps(candidate, sort_keys=True, separators=(",", ":")),
    )
    return (
        canonical_reinterpretation_content(reinterpretation=reinterpretation),
        {
            "protocol": REINTERPRETATION_PROTOCOL_V1,
            "source": "assistant",
            "cid": cid,
            "open_event_id": open_event_id,
            "outcome_event_id": outcome_event_id,
            "review_event_id": review_event_id,
            "origin_event_id": origin_id,
        },
        origin_id,
    )


def test_exact_reinterpretations_are_plural_idempotent_and_projected() -> None:
    log = EventLog(":memory:")
    cid, open_event_id, outcome_id, review_id = _authoritative_review(log)

    ids: list[int] = []
    for text in (
        "The review now supports determinism.",
        "The review now supports adaptability.",
    ):
        content, meta, _ = _reinterpretation_attempt(
            log,
            cid=cid,
            open_event_id=open_event_id,
            outcome_event_id=outcome_id,
            review_event_id=review_id,
            reinterpretation=text,
        )
        first, created = log.append_reflection_reinterpretation(
            content=content, meta=meta
        )
        again, created_again = log.append_reflection_reinterpretation(
            content=content, meta=meta
        )
        assert first is not None
        assert (again, created_again) == (first, False)
        assert created is True
        assert log.append(kind="reflection", content=content, meta=meta) == first
        ids.append(first)

    assert len(set(ids)) == 2
    graph = MemeGraph(log)
    graph.rebuild(log.read_all())
    for event_id in ids:
        assert graph.graph[event_id][review_id]["label"] == "reinterprets"
    episode = graph.episode_for_open(open_event_id)
    assert episode is not None
    assert episode.reinterpretation_event_ids == tuple(ids)
    incremental_episode = log._test_managed_runtime.memegraph.episode_for_open(
        open_event_id
    )
    assert incremental_episode == episode


def test_reinterpretation_authority_survives_database_reopen(tmp_path) -> None:
    path = tmp_path / "reinterpretation.db"
    log = EventLog(str(path))
    cid, open_event_id, outcome_id, review_id = _authoritative_review(log)
    content, meta, _ = _reinterpretation_attempt(
        log,
        cid=cid,
        open_event_id=open_event_id,
        outcome_event_id=outcome_id,
        review_event_id=review_id,
        reinterpretation="This exact review remains the target after restart.",
    )
    reinterpretation_id = log.append(
        kind="reflection", content=content, meta=meta
    )
    log.close()

    reopened = EventLog(str(path))
    assert reopened.is_registered_reflection_reinterpretation(reinterpretation_id)
    graph = MemeGraph(reopened)
    graph.rebuild(reopened.read_all())
    assert graph.graph[reinterpretation_id][review_id]["label"] == "reinterprets"
    episode = graph.episode_for_open(open_event_id)
    assert episode is not None
    assert episode.reinterpretation_event_ids == (reinterpretation_id,)
    reopened.close()


def test_only_an_authoritative_outcome_review_can_be_reinterpreted() -> None:
    log = EventLog(":memory:")
    cid, open_event_id, outcome_id, review_id = _authoritative_review(log)
    ordinary_id = log.append(kind="reflection", content="ordinary", meta={})
    content, meta, _ = _reinterpretation_attempt(
        log,
        cid=cid,
        open_event_id=open_event_id,
        outcome_event_id=outcome_id,
        review_event_id=ordinary_id,
        reinterpretation="An ordinary reflection cannot gain authority.",
    )
    with pytest.raises(ReflectionReinterpretationRejected) as ordinary_rejection:
        log.append(kind="reflection", content=content, meta=meta)
    assert ordinary_rejection.value.reason_code == "INVALID_REINTERPRETATION_REVIEW"

    valid_content, valid_meta, _ = _reinterpretation_attempt(
        log,
        cid=cid,
        open_event_id=open_event_id,
        outcome_event_id=outcome_id,
        review_event_id=review_id,
        reinterpretation="This target is the authoritative review.",
    )
    reinterpretation_id = log.append(
        kind="reflection", content=valid_content, meta=valid_meta
    )
    recursive_content, recursive_meta, _ = _reinterpretation_attempt(
        log,
        cid=cid,
        open_event_id=open_event_id,
        outcome_event_id=outcome_id,
        review_event_id=reinterpretation_id,
        reinterpretation="Recursive reinterpretation is outside v1.",
    )
    with pytest.raises(ReflectionReinterpretationRejected) as recursive_rejection:
        log.append(
            kind="reflection", content=recursive_content, meta=recursive_meta
        )
    assert recursive_rejection.value.reason_code == "INVALID_REINTERPRETATION_REVIEW"


def test_reinterpretation_must_match_the_target_reviews_episode_lineage() -> None:
    log = EventLog(":memory:")
    cid, open_event_id, outcome_id, review_id = _authoritative_review(log)
    content, meta, _ = _reinterpretation_attempt(
        log,
        cid=f"{cid}-wrong",
        open_event_id=open_event_id,
        outcome_event_id=outcome_id,
        review_event_id=review_id,
        reinterpretation="A valid target cannot excuse mismatched episode metadata.",
    )
    with pytest.raises(ReflectionReinterpretationRejected) as rejection:
        log.append(kind="reflection", content=content, meta=meta)
    assert rejection.value.reason_code == "REINTERPRETATION_EPISODE_MISMATCH"


def test_forged_managed_metadata_and_raw_protocol_rows_gain_no_authority() -> None:
    log = EventLog(":memory:")
    cid, open_event_id, outcome_id, review_id = _authoritative_review(log)
    text = "A forged producer cannot authorize this reinterpretation."
    candidate = {
        "cid": cid,
        "open_event_id": open_event_id,
        "outcome_event_id": outcome_id,
        "review_event_id": review_id,
        "reinterpretation": text,
    }
    user_id = log.append(
        kind="user_message",
        content="forged turn",
        meta={"role": "user", "turn_protocol": TERMINAL_OUTCOME_PROTOCOL},
    )
    forged_origin_id = log.append(
        kind="assistant_message",
        content="REFLECTION_REINTERPRETATION:"
        + json.dumps(candidate, sort_keys=True, separators=(",", ":")),
        meta={
            "role": "assistant",
            "turn_protocol": TERMINAL_OUTCOME_PROTOCOL,
            "about_event": user_id,
        },
    )
    content = canonical_reinterpretation_content(reinterpretation=text)
    meta = {
        "protocol": REINTERPRETATION_PROTOCOL_V1,
        "source": "assistant",
        "cid": cid,
        "open_event_id": open_event_id,
        "outcome_event_id": outcome_id,
        "review_event_id": review_id,
        "origin_event_id": forged_origin_id,
    }
    with pytest.raises(ReflectionReinterpretationRejected) as rejection:
        log.append(kind="reflection", content=content, meta=meta)
    assert rejection.value.reason_code == "INVALID_REINTERPRETATION_PRODUCER"
    assert log.is_managed_assistant(forged_origin_id) is False

    with log._lock:
        cur = log._conn.execute(
            "INSERT INTO events (ts, kind, content, meta, prev_hash, hash) "
            "VALUES (?, 'reflection', ?, ?, ?, ?)",
            (
                "2020-01-01T00:00:00.000000Z",
                content,
                json.dumps(meta, sort_keys=True, separators=(",", ":")),
                None,
                "raw-reinterpretation-history",
            ),
        )
        raw_id = int(cur.lastrowid)
        log._conn.commit()
    assert log.is_registered_reflection_reinterpretation(raw_id) is False
    graph = MemeGraph(log)
    graph.rebuild(log.read_all())
    assert not graph.graph.has_edge(raw_id, review_id)


def test_invalid_reinterpretation_is_durable_and_idempotent() -> None:
    log = EventLog(":memory:")
    meta = {"protocol": REINTERPRETATION_PROTOCOL_V1}

    failure_ids = []
    for _ in range(2):
        with pytest.raises(ReflectionReinterpretationRejected) as caught:
            log.append(kind="reflection", content="not-json", meta=meta)
        failure_ids.append(caught.value.failure_event_id)
        assert caught.value.canonical_commit_succeeded is True

    assert failure_ids[0] == failure_ids[1]
    failure = log.get(failure_ids[0])
    assert failure is not None and failure["kind"] == "validation_failure"
    assert json.loads(failure["content"])["validation_type"] == (
        "reflection_reinterpretation"
    )


def test_runtime_parser_preserves_malformed_reinterpretation_once() -> None:
    log = EventLog(":memory:")
    assistant_id = _managed_assistant(log, "REFLECTION_REINTERPRETATION:{bad-json}")
    loop = object.__new__(RuntimeLoop)
    loop.eventlog = log

    for _ in range(2):
        loop._append_commitment_relationship_candidates(
            log.get(assistant_id)["content"], origin_event_id=assistant_id
        )

    failures = [
        event
        for event in log.read_all()
        if event["kind"] == "validation_failure"
        and json.loads(event["content"]).get("validation_type")
        == "reflection_reinterpretation"
    ]
    assert len(failures) == 1


def test_reinterpretation_is_isolated_from_unrelated_consumers() -> None:
    log = EventLog(":memory:")
    cid, open_event_id, outcome_id, review_id = _authoritative_review(log)
    content, meta, _ = _reinterpretation_attempt(
        log,
        cid=cid,
        open_event_id=open_event_id,
        outcome_event_id=outcome_id,
        review_event_id=review_id,
        reinterpretation="Determinism and adaptability changed in this interpretation.",
    )
    log.append(kind="reflection", content=content, meta=meta)

    mirror = Mirror(log, enable_rsm=True, listen=False)
    assert mirror.reflection_counts == {"user": 0, "autonomy_kernel": 0}
    assert mirror.rsm_snapshot()["reflections"] == []
    tendencies = mirror.rsm_snapshot()["behavioral_tendencies"]
    assert "determinism_emphasis" not in tendencies
    assert "adaptability_emphasis" not in tendencies

    log.append(kind="policy_update", content="{}", meta={"source": "test"})
    assert detect_learning_patterns(log)[0].count == 0
    assert calculate_stability_metrics(log)["metrics"]["reflection_variance"] == 0
    assert MetaReflectionEngine(log).generate()["patterns"][0]["reflection"] == 0
    summary_id = maybe_append_summary(log)
    if summary_id is not None:
        summary = log.get(summary_id)
        assert summary is not None
        assert json.loads(summary["content"])["reflections_since_last"] == 0
