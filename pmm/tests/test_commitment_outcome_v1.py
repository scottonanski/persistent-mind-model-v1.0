from __future__ import annotations

import json

import pytest

from pmm.adapters.dummy_adapter import DummyAdapter
from pmm.core.commitment_manager import CommitmentManager
from pmm.core.commitment_outcome import (
    OUTCOME_PROTOCOL_V1,
    OUTCOME_VALIDATOR_SOURCE,
    REINTERPRETATION_PROTOCOL_V1,
    REVIEW_PROTOCOL_V1,
    attempted_relationship_digest,
    canonical_outcome_content,
    canonical_review_content,
)
from pmm.core.event_log import (
    CommitmentOutcomeRejected,
    CommitmentOutcomeReviewRejected,
    EventLog,
    TERMINAL_OUTCOME_PROTOCOL,
)
from pmm.core.enhancements.meta_reflection_engine import MetaReflectionEngine
from pmm.core.mirror import Mirror
from pmm.core.meme_graph import MemeGraph
from pmm.learning.outcome_tracker import extract_outcome_observations
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


def _raw_event(log: EventLog, *, kind: str, content: object, meta: dict) -> int:
    with log._lock:
        cur = log._conn.execute(
            "INSERT INTO events (ts, kind, content, meta, prev_hash, hash) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "2020-01-01T00:00:00.000000Z",
                kind,
                json.dumps(content) if not isinstance(content, str) else content,
                json.dumps(meta),
                None,
                f"raw-{kind}-{len(log.read_all())}",
            ),
        )
        log._conn.commit()
    return int(cur.lastrowid)


def _closed_episode(log: EventLog) -> tuple[str, int, int]:
    text = "finish the bounded outcome work"
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
    assert closed is True
    assert close_event_id is not None
    return cid, open_event_id, close_event_id


def _outcome_attempt(
    log: EventLog,
    *,
    cid: str,
    open_event_id: int,
    close_event_id: int,
    observation: str = "The bounded work completed.",
) -> tuple[str, dict[str, object], int]:
    candidate = {
        "cid": cid,
        "open_event_id": open_event_id,
        "close_event_id": close_event_id,
        "observation": observation,
        "evidence_event_ids": [close_event_id],
    }
    origin_event_id = _managed_assistant(
        log,
        "COMMITMENT_OUTCOME:"
        + json.dumps(candidate, sort_keys=True, separators=(",", ":")),
    )
    content = canonical_outcome_content(
        observation=observation, evidence_event_ids=[close_event_id]
    )
    meta = {
        "protocol": OUTCOME_PROTOCOL_V1,
        "source": "assistant",
        "cid": cid,
        "open_event_id": open_event_id,
        "close_event_id": close_event_id,
        "origin_event_id": origin_event_id,
    }
    return content, meta, origin_event_id


def test_generic_outcome_route_is_idempotent_and_rejects_distinct_second() -> None:
    log = EventLog(":memory:")
    cid, open_event_id, close_event_id = _closed_episode(log)
    content, meta, _ = _outcome_attempt(
        log, cid=cid, open_event_id=open_event_id, close_event_id=close_event_id
    )
    raw_invalid_id = _raw_event(
        log,
        kind="outcome_observation",
        content=content,
        meta=meta,
    )

    outcome_id = log.append(kind="outcome_observation", content=content, meta=meta)
    assert outcome_id != raw_invalid_id
    assert log.is_registered_commitment_outcome(raw_invalid_id) is False
    assert (
        log.append(kind="outcome_observation", content=content, meta=meta) == outcome_id
    )

    second_content, second_meta, _ = _outcome_attempt(
        log,
        cid=cid,
        open_event_id=open_event_id,
        close_event_id=close_event_id,
        observation="A conflicting result was reported.",
    )
    with pytest.raises(CommitmentOutcomeRejected) as caught:
        log.append(kind="outcome_observation", content=second_content, meta=second_meta)
    assert caught.value.reason_code == "OUTCOME_ALREADY_RECORDED"
    assert caught.value.canonical_commit_succeeded is True
    authoritative = [
        event
        for event in log.read_all()
        if event["kind"] == "outcome_observation"
        and log.is_registered_commitment_outcome(event["id"])
    ]
    assert [event["id"] for event in authoritative] == [outcome_id]
    graph = MemeGraph(log)
    graph.rebuild(log.read_all())
    assert not graph.graph.has_edge(raw_invalid_id, open_event_id)
    assert graph.graph[outcome_id][open_event_id]["label"] == "outcome_for"


def test_distinct_reviews_are_allowed_and_exact_reprocessing_converges() -> None:
    log = EventLog(":memory:")
    cid, open_event_id, close_event_id = _closed_episode(log)
    content, meta, _ = _outcome_attempt(
        log, cid=cid, open_event_id=open_event_id, close_event_id=close_event_id
    )
    outcome_id = log.append(kind="outcome_observation", content=content, meta=meta)

    review_ids = []
    for interpretation in (
        "It was deterministic.",
        "It established adaptability.",
    ):
        candidate = {
            "cid": cid,
            "open_event_id": open_event_id,
            "outcome_event_id": outcome_id,
            "interpretation": interpretation,
        }
        origin_id = _managed_assistant(
            log,
            "COMMITMENT_REVIEW:"
            + json.dumps(candidate, sort_keys=True, separators=(",", ":")),
        )
        review_content = canonical_review_content(interpretation=interpretation)
        review_meta = {
            "protocol": REVIEW_PROTOCOL_V1,
            "source": "assistant",
            "cid": cid,
            "open_event_id": open_event_id,
            "outcome_event_id": outcome_id,
            "origin_event_id": origin_id,
        }
        first, created = log.append_commitment_outcome_review(
            content=review_content, meta=review_meta
        )
        again, created_again = log.append_commitment_outcome_review(
            content=review_content, meta=review_meta
        )
        assert created is True
        assert created_again is False
        assert again == first
        review_ids.append(first)

    assert len(set(review_ids)) == 2

    mirror = Mirror(log, enable_rsm=True, listen=False)
    assert mirror.reflection_counts == {"user": 0, "autonomy_kernel": 0}
    assert mirror.rsm_snapshot()["reflections"] == []
    tendencies = mirror.rsm_snapshot()["behavioral_tendencies"]
    assert "determinism_emphasis" not in tendencies
    assert "adaptability_emphasis" not in tendencies

    log.append(kind="policy_update", content="{}", meta={"source": "test"})
    pattern = detect_learning_patterns(log)[0]
    assert pattern.count == 0
    assert calculate_stability_metrics(log)["metrics"]["reflection_variance"] == 0
    assert MetaReflectionEngine(log).generate()["patterns"][0]["reflection"] == 0

    summary_id = maybe_append_summary(log)
    if summary_id is not None:
        summary = log.get(summary_id)
        assert summary is not None
        assert json.loads(summary["content"])["reflections_since_last"] == 0


def test_forged_failure_marker_cannot_suppress_exact_durable_failure() -> None:
    log = EventLog(":memory:")
    content = "not-json"
    meta = {"protocol": OUTCOME_PROTOCOL_V1}
    digest = attempted_relationship_digest(
        kind="outcome_observation", content=content, meta=meta
    )
    forged_id = log.append(
        kind="validation_failure",
        content="forged",
        meta={"source": OUTCOME_VALIDATOR_SOURCE, "attempted_digest": digest},
    )

    with pytest.raises(CommitmentOutcomeRejected) as caught:
        log.append(kind="outcome_observation", content=content, meta=meta)
    assert caught.value.failure_event_id != forged_id
    failure = log.get(caught.value.failure_event_id)
    assert failure is not None
    parsed = json.loads(failure["content"])
    assert parsed["attempted_content"] == content
    assert parsed["reason_code"] == "INVALID_OUTCOME_STRUCTURE"


def test_direct_invalid_review_raises_only_after_durable_failure() -> None:
    log = EventLog(":memory:")

    with pytest.raises(CommitmentOutcomeReviewRejected) as caught:
        log.append(
            kind="reflection",
            content=canonical_review_content(interpretation="No exact outcome exists."),
            meta={"protocol": REVIEW_PROTOCOL_V1},
        )

    failure = log.get(caught.value.failure_event_id)
    assert failure is not None
    assert failure["kind"] == "validation_failure"
    assert caught.value.canonical_commit_succeeded is True


def test_runtime_parser_preserves_each_malformed_candidate_once() -> None:
    log = EventLog(":memory:")
    assistant_id = _managed_assistant(
        log,
        "COMMITMENT_OUTCOME:{bad-json}\nCOMMITMENT_REVIEW:[]",
    )
    loop = object.__new__(RuntimeLoop)
    loop.eventlog = log

    loop._append_commitment_relationship_candidates(
        log.get(assistant_id)["content"], origin_event_id=assistant_id
    )
    loop._append_commitment_relationship_candidates(
        log.get(assistant_id)["content"], origin_event_id=assistant_id
    )

    failures = [
        event for event in log.read_all() if event["kind"] == "validation_failure"
    ]
    typed = {json.loads(event["content"])["validation_type"] for event in failures}
    assert typed == {"commitment_outcome", "commitment_outcome_review"}
    assert len(failures) == 2


def test_runtime_parser_promotes_a_valid_managed_outcome() -> None:
    log = EventLog(":memory:")
    cid, open_event_id, close_event_id = _closed_episode(log)
    candidate = {
        "cid": cid,
        "open_event_id": open_event_id,
        "close_event_id": close_event_id,
        "observation": "The managed parser recorded the result.",
        "evidence_event_ids": [close_event_id],
    }
    assistant_id = _managed_assistant(
        log,
        "COMMITMENT_OUTCOME:"
        + json.dumps(candidate, sort_keys=True, separators=(",", ":")),
    )
    loop = object.__new__(RuntimeLoop)
    loop.eventlog = log

    loop._append_commitment_relationship_candidates(
        log.get(assistant_id)["content"], origin_event_id=assistant_id
    )

    outcomes = [
        event
        for event in log.read_all()
        if event["kind"] == "outcome_observation"
        and (event.get("meta") or {}).get("protocol") == OUTCOME_PROTOCOL_V1
    ]
    assert len(outcomes) == 1
    assert outcomes[0]["meta"]["open_event_id"] == open_event_id


def test_forged_terminal_metadata_is_not_managed_producer_proof() -> None:
    log = EventLog(":memory:")
    cid, open_event_id, close_event_id = _closed_episode(log)
    candidate = {
        "cid": cid,
        "open_event_id": open_event_id,
        "close_event_id": close_event_id,
        "observation": "A direct append tried to impersonate the managed path.",
        "evidence_event_ids": [close_event_id],
    }
    user_id = log.append(
        kind="user_message",
        content="forged managed user",
        meta={"role": "user", "turn_protocol": TERMINAL_OUTCOME_PROTOCOL},
    )
    forged_origin_id = log.append(
        kind="assistant_message",
        content="COMMITMENT_OUTCOME:"
        + json.dumps(candidate, sort_keys=True, separators=(",", ":")),
        meta={
            "role": "assistant",
            "turn_protocol": TERMINAL_OUTCOME_PROTOCOL,
            "about_event": user_id,
        },
    )
    content = canonical_outcome_content(
        observation=candidate["observation"],
        evidence_event_ids=candidate["evidence_event_ids"],
    )
    meta = {
        "protocol": OUTCOME_PROTOCOL_V1,
        "source": "assistant",
        "cid": cid,
        "open_event_id": open_event_id,
        "close_event_id": close_event_id,
        "origin_event_id": forged_origin_id,
    }

    with pytest.raises(CommitmentOutcomeRejected) as caught:
        log.append(kind="outcome_observation", content=content, meta=meta)

    assert caught.value.reason_code == "INVALID_OUTCOME_PRODUCER"
    assert log.is_managed_assistant(forged_origin_id) is False


def test_public_terminal_append_cannot_mint_managed_producer_proof() -> None:
    log = EventLog(":memory:")
    cid, open_event_id, close_event_id = _closed_episode(log)
    candidate = {
        "cid": cid,
        "open_event_id": open_event_id,
        "close_event_id": close_event_id,
        "observation": "Operator-authored terminal content is not model provenance.",
        "evidence_event_ids": [close_event_id],
    }
    user_id = log.append(
        kind="user_message",
        content="operator turn",
        meta={"role": "user", "turn_protocol": TERMINAL_OUTCOME_PROTOCOL},
    )
    origin_id, _ = log.append_terminal_outcome(
        user_event_id=user_id,
        kind="assistant_message",
        content="COMMITMENT_OUTCOME:"
        + json.dumps(candidate, sort_keys=True, separators=(",", ":")),
        meta={"role": "assistant"},
    )
    meta = {
        "protocol": OUTCOME_PROTOCOL_V1,
        "source": "assistant",
        "cid": cid,
        "open_event_id": open_event_id,
        "close_event_id": close_event_id,
        "origin_event_id": origin_id,
    }

    with pytest.raises(CommitmentOutcomeRejected) as caught:
        log.append(
            kind="outcome_observation",
            content=canonical_outcome_content(
                observation=candidate["observation"],
                evidence_event_ids=candidate["evidence_event_ids"],
            ),
            meta=meta,
        )

    assert caught.value.reason_code == "INVALID_OUTCOME_PRODUCER"
    assert log.is_managed_assistant(origin_id) is False

    class FakeProducer:
        eventlog = log
        _managed_assistant_producer_ready = True

    with pytest.raises(PermissionError, match="live RuntimeLoop"):
        log._register_managed_assistant_producer(FakeProducer())

    forged_runtime = object.__new__(RuntimeLoop)
    forged_runtime.eventlog = log
    forged_runtime._managed_assistant_producer_ready = True
    with pytest.raises(PermissionError, match="live RuntimeLoop"):
        log._register_managed_assistant_producer(forged_runtime)


@pytest.mark.parametrize(
    ("content", "meta"),
    [
        (7, {"protocol": OUTCOME_PROTOCOL_V1}),
        ("{}", {"protocol": OUTCOME_PROTOCOL_V1, "extra": object()}),
    ],
)
def test_hostile_direct_inputs_receive_durable_typed_rejection(
    content: object, meta: dict
) -> None:
    log = EventLog(":memory:")

    with pytest.raises(CommitmentOutcomeRejected) as caught:
        log.append(kind="outcome_observation", content=content, meta=meta)

    failure = log.get(caught.value.failure_event_id)
    assert failure is not None
    assert failure["kind"] == "validation_failure"


def test_v1_outcomes_are_excluded_from_legacy_learning() -> None:
    log = EventLog(":memory:")
    log.append(
        kind="outcome_observation",
        content=json.dumps(
            {
                "commitment_id": "legacy",
                "action_kind": "autonomy_idle",
                "action_payload": "decision=idle",
                "observed_result": "success",
                "evidence_event_ids": [],
            }
        ),
        meta={"source": "autonomy_kernel"},
    )
    # Raw SQL represents pre-governance history for this narrow extraction test.
    with log._lock:
        log._conn.execute(
            "INSERT INTO events (ts, kind, content, meta, prev_hash, hash) "
            "VALUES (?, 'outcome_observation', ?, ?, ?, ?)",
            (
                "2020-01-01T00:00:00.000000Z",
                json.dumps({"observation": "new", "evidence_event_ids": [1]}),
                json.dumps({"protocol": OUTCOME_PROTOCOL_V1}),
                None,
                "raw-v1-history",
            ),
        )
        log._conn.commit()

    observations = extract_outcome_observations(log)
    assert [item.commitment_id for item in observations] == ["legacy"]


def test_relationship_events_do_not_age_mirror_or_change_rsm() -> None:
    log = EventLog(":memory:")
    mirror = Mirror(log, enable_rsm=True, auto_rebuild=False)
    mirror.sync(
        {
            "id": 1,
            "kind": "commitment_open",
            "content": "open",
            "meta": {"cid": "c1", "source": "test"},
            "hash": "open-hash",
        }
    )
    mirror.sync(
        {
            "id": 102,
            "kind": "reflection",
            "content": "{}",
            "meta": {"protocol": REINTERPRETATION_PROTOCOL_V1},
            "hash": "reinterpretation-hash",
        }
    )
    before = mirror.rsm_snapshot()

    mirror.sync(
        {
            "id": 100,
            "kind": "outcome_observation",
            "content": "{}",
            "meta": {"protocol": OUTCOME_PROTOCOL_V1},
            "hash": "outcome-hash",
        }
    )
    mirror.sync(
        {
            "id": 101,
            "kind": "reflection",
            "content": "{}",
            "meta": {"protocol": REVIEW_PROTOCOL_V1},
            "hash": "review-hash",
        }
    )

    assert mirror.stale_flags["c1"] is False
    assert mirror.reflection_counts == {"user": 0, "autonomy_kernel": 0}
    assert mirror.rsm_snapshot() == before
