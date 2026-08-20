# SPDX-License-Identifier: PMM-1.0

from __future__ import annotations

import json

from pmm.adapters.dummy_adapter import DummyAdapter
from pmm.core.commitment_outcome import (
    OUTCOME_PROTOCOL_V1,
    REVIEW_PROTOCOL_V1,
    canonical_outcome_content,
    canonical_review_content,
)
from pmm.core.commitment_manager import CommitmentManager
from pmm.core.event_log import EventLog, TERMINAL_OUTCOME_PROTOCOL, _canonical_json
from pmm.core.meme_graph import CommitmentOrigin, MemeGraph
from pmm.runtime.loop import RuntimeLoop


def _assistant(log: EventLog, content: str) -> int:
    return log.append(
        kind="assistant_message",
        content=content,
        meta={"role": "assistant"},
    )


def _open(log: EventLog, *, cid: str, text: str, assistant_id: int) -> int:
    return log.append(
        kind="commitment_open",
        content=f"Commitment opened: {text}",
        meta={
            "cid": cid,
            "origin": "assistant",
            "source": "assistant",
            "text": text,
            "origin_event_id": assistant_id,
        },
    )


def _incremental(log: EventLog) -> MemeGraph:
    graph = MemeGraph(log)
    for event in log.read_all():
        graph.add_event(event)
    return graph


def _managed_assistant(log: EventLog, content: str) -> int:
    producer = getattr(log, "_test_managed_runtime", None)
    if producer is None:
        producer = RuntimeLoop(eventlog=log, adapter=DummyAdapter(), autonomy=False)
        log._test_managed_runtime = producer
    user_id = log.append(
        kind="user_message",
        content="record the structured relationship",
        meta={"role": "user", "turn_protocol": TERMINAL_OUTCOME_PROTOCOL},
    )
    assistant_id, _ = log._append_managed_assistant_outcome(
        producer=producer,
        user_event_id=user_id,
        content=content,
        meta={"role": "assistant"},
    )
    return assistant_id


def test_history_preserves_episode_boundaries_and_current_view() -> None:
    log = EventLog(":memory:")
    cid = "c1"
    text = "finish the audit"

    opening_assistant = _assistant(log, f"COMMIT: {text}")
    first_open = _open(
        log,
        cid=cid,
        text=text,
        assistant_id=opening_assistant,
    )
    opening_reflection = log.append(
        kind="reflection",
        content="The commitment was opened.",
        meta={"about_event": opening_assistant},
    )
    closing_assistant = _assistant(log, f"Done.\nCLOSE: {cid}")
    first_close = CommitmentManager(log).close_commitment(
        cid,
        source="assistant",
        origin_event_id=closing_assistant,
    )
    closing_reflection = log.append(
        kind="reflection",
        content="The commitment was closed.",
        meta={"about_event": closing_assistant},
    )

    reopening_assistant = _assistant(log, f"COMMIT: {text}")
    second_open = _open(
        log,
        cid=cid,
        text=text,
        assistant_id=reopening_assistant,
    )

    rebuilt = MemeGraph(log)
    rebuilt.rebuild(log.read_all())
    incremental = _incremental(log)

    for graph in (rebuilt, incremental):
        history = graph.history_for_cid(cid)
        assert [episode.open_event_id for episode in history] == [
            first_open,
            second_open,
        ]

        first, second = history
        assert first.status == "closed"
        assert first.opening_origin == CommitmentOrigin(opening_assistant, "explicit")
        assert [(closure.event_id, closure.origin) for closure in first.closures] == [
            (
                first_close,
                CommitmentOrigin(closing_assistant, "explicit"),
            )
        ]
        assert first.reflection_event_ids == (
            opening_reflection,
            closing_reflection,
        )
        assert first.event_ids == (
            opening_assistant,
            first_open,
            closing_assistant,
            first_close,
            opening_reflection,
            closing_reflection,
        )
        assert first.chronological_event_ids == (
            opening_assistant,
            first_open,
            opening_reflection,
            closing_assistant,
            first_close,
            closing_reflection,
        )

        assert second.status == "open"
        assert second.opening_origin == CommitmentOrigin(
            reopening_assistant, "explicit"
        )
        assert second.closures == ()
        assert second.event_ids == (reopening_assistant, second_open)
        assert graph.current_episode_for_cid(cid) == second
        assert graph.episode_for_open(first_open) == first
        assert graph.thread_for_cid(cid) == list(second.event_ids)

    assert rebuilt.history_for_cid(cid) == incremental.history_for_cid(cid)


def test_legacy_episode_labels_inference_without_inventing_close_origin() -> None:
    log = EventLog(":memory:")
    assistant_id = _assistant(log, "COMMIT: legacy task")
    open_event_id = log.append(
        kind="commitment_open",
        content="legacy open",
        meta={"cid": "legacy", "source": "assistant", "text": "legacy task"},
    )
    close_event_id = log.append(
        kind="commitment_close",
        content="legacy close",
        meta={"cid": "legacy", "source": "test_fixture"},
    )

    graph = MemeGraph(log)
    graph.rebuild(log.read_all())
    episode = graph.episode_for_open(open_event_id)

    assert episode is not None
    assert episode.opening_origin == CommitmentOrigin(assistant_id, "legacy_inferred")
    assert episode.closures[0].event_id == close_event_id
    assert episode.closures[0].origin == CommitmentOrigin(None, "absent")
    assert episode.status == "closed"


def test_legacy_reopen_uses_latest_prior_assistant_without_episode_bleed() -> None:
    log = EventLog(":memory:")
    first_assistant = _assistant(log, "COMMIT: repeated task")
    first_open = log.append(
        kind="commitment_open",
        content="first legacy open",
        meta={"cid": "legacy", "source": "assistant", "text": "repeated task"},
    )
    first_reflection = log.append(
        kind="reflection",
        content="first episode reflection",
        meta={"about_event": first_assistant},
    )
    log.append(
        kind="commitment_close",
        content="first legacy close",
        meta={"cid": "legacy", "source": "test_fixture"},
    )
    second_assistant = _assistant(log, "COMMIT: repeated task")
    second_open = log.append(
        kind="commitment_open",
        content="second legacy open",
        meta={"cid": "legacy", "source": "assistant", "text": "repeated task"},
    )

    rebuilt = MemeGraph(log)
    rebuilt.rebuild(log.read_all())
    incremental = _incremental(log)

    for graph in (rebuilt, incremental):
        first, second = graph.history_for_cid("legacy")
        assert first.open_event_id == first_open
        assert first.opening_origin == CommitmentOrigin(
            first_assistant, "legacy_inferred"
        )
        assert first_reflection in first.reflection_event_ids

        assert second.open_event_id == second_open
        assert second.opening_origin == CommitmentOrigin(
            second_assistant, "legacy_inferred"
        )
        assert first_assistant not in second.event_ids
        assert first_reflection not in second.reflection_event_ids
        assert graph.current_episode_for_cid("legacy") == second
        assert graph.thread_for_cid("legacy") == [second_assistant, second_open]


def test_malformed_explicit_origins_remain_invalid_in_episode_view() -> None:
    log = EventLog(":memory:")
    opening_assistant = _assistant(log, "COMMIT: task")
    open_event_id = _open(
        log,
        cid="c1",
        text="task",
        assistant_id=opening_assistant,
    )
    closing_assistant = _assistant(log, "CLOSE: c1")
    close_event_id = CommitmentManager(log).close_commitment(
        "c1",
        source="assistant",
        origin_event_id=closing_assistant,
    )
    close_event = log.get(close_event_id or 0)
    assert close_event is not None
    with log._lock:
        log._conn.execute(
            "UPDATE events SET meta = ? WHERE id = ?",
            (
                _canonical_json(
                    {
                        **close_event["meta"],
                        "origin_event_id": 9999,
                    }
                ),
                close_event_id,
            ),
        )

    graph = MemeGraph(log)
    graph.rebuild(log.read_all())
    episode = graph.episode_for_open(open_event_id)

    assert episode is not None
    assert episode.opening_origin == CommitmentOrigin(opening_assistant, "explicit")
    assert episode.closures[0].origin == CommitmentOrigin(None, "invalid_explicit")
    assert closing_assistant not in episode.event_ids


def test_malformed_explicit_open_origin_does_not_use_legacy_fallback() -> None:
    log = EventLog(":memory:")
    assistant_id = _assistant(log, "COMMIT: task")
    open_event_id = _open(
        log,
        cid="c1",
        text="task",
        assistant_id=assistant_id,
    )
    open_event = log.get(open_event_id)
    assert open_event is not None
    with log._lock:
        log._conn.execute(
            "UPDATE events SET meta = ? WHERE id = ?",
            (
                _canonical_json(
                    {
                        **open_event["meta"],
                        "origin_event_id": 9999,
                    }
                ),
                open_event_id,
            ),
        )

    graph = MemeGraph(log)
    graph.rebuild(log.read_all())
    episode = graph.episode_for_open(open_event_id)

    assert episode is not None
    assert episode.opening_origin == CommitmentOrigin(None, "invalid_explicit")
    assert assistant_id not in episode.event_ids


def test_episode_queries_reject_non_open_and_unknown_inputs() -> None:
    log = EventLog(":memory:")
    user_id = log.append(kind="user_message", content="hello", meta={})
    graph = MemeGraph(log)
    graph.rebuild(log.read_all())

    assert graph.episode_for_open(user_id) is None
    assert graph.episode_for_open(True) is None
    assert graph.episode_for_open(9999) is None
    assert graph.history_for_cid("") == []
    assert graph.history_for_cid("missing") == []
    assert graph.current_episode_for_cid("missing") is None


def test_authoritative_outcome_and_reviews_are_exact_episode_members() -> None:
    log = EventLog(":memory:")
    cid = "c1"
    opening_assistant = _assistant(log, "COMMIT: observe the result")
    open_event_id = _open(
        log,
        cid=cid,
        text="observe the result",
        assistant_id=opening_assistant,
    )
    closing_assistant = _assistant(log, f"CLOSE: {cid}")
    close_event_id = CommitmentManager(log).close_commitment(
        cid,
        source="assistant",
        origin_event_id=closing_assistant,
    )
    assert close_event_id is not None

    outcome_candidate = {
        "cid": cid,
        "open_event_id": open_event_id,
        "close_event_id": close_event_id,
        "observation": "The bounded work completed.",
        "evidence_event_ids": [close_event_id],
    }
    outcome_origin = _managed_assistant(
        log,
        "COMMITMENT_OUTCOME:"
        + json.dumps(outcome_candidate, sort_keys=True, separators=(",", ":")),
    )
    outcome_event_id = log.append(
        kind="outcome_observation",
        content=canonical_outcome_content(
            observation=outcome_candidate["observation"],
            evidence_event_ids=outcome_candidate["evidence_event_ids"],
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

    review_ids: list[int] = []
    for interpretation in (
        "It proved the boundary.",
        "It also exposed follow-up work.",
    ):
        review_candidate = {
            "cid": cid,
            "open_event_id": open_event_id,
            "outcome_event_id": outcome_event_id,
            "interpretation": interpretation,
        }
        review_origin = _managed_assistant(
            log,
            "COMMITMENT_REVIEW:"
            + json.dumps(review_candidate, sort_keys=True, separators=(",", ":")),
        )
        review_ids.append(
            log.append(
                kind="reflection",
                content=canonical_review_content(interpretation=interpretation),
                meta={
                    "protocol": REVIEW_PROTOCOL_V1,
                    "source": "assistant",
                    "cid": cid,
                    "open_event_id": open_event_id,
                    "outcome_event_id": outcome_event_id,
                    "origin_event_id": review_origin,
                },
            )
        )

    reopening_assistant = _assistant(log, "COMMIT: observe the result")
    reopened_event_id = _open(
        log,
        cid=cid,
        text="observe the result",
        assistant_id=reopening_assistant,
    )

    rebuilt = MemeGraph(log)
    rebuilt.rebuild(log.read_all())
    incremental = _incremental(log)

    for graph in (rebuilt, incremental):
        episode = graph.episode_for_open(open_event_id)
        assert episode is not None
        assert episode.status == "closed"
        assert episode.outcome_event_id == outcome_event_id
        assert episode.review_event_ids == tuple(review_ids)
        assert episode.event_ids[-3:] == (outcome_event_id, *review_ids)
        assert graph.graph[outcome_event_id][open_event_id]["label"] == "outcome_for"
        assert all(
            graph.graph[review_id][outcome_event_id]["label"] == "reviews_outcome"
            for review_id in review_ids
        )
        assert graph.cids_for_event(outcome_event_id) == [cid]
        assert all(graph.cids_for_event(review_id) == [cid] for review_id in review_ids)
        assert graph.episodes_for_event(outcome_event_id) == [episode]
        assert all(
            graph.episodes_for_event(review_id) == [episode] for review_id in review_ids
        )
        current = graph.current_episode_for_cid(cid)
        assert current is not None
        assert current.open_event_id == reopened_event_id
        assert current.outcome_event_id is None
        assert current.review_event_ids == ()
        assert outcome_event_id not in current.event_ids
        assert all(review_id not in current.event_ids for review_id in review_ids)

    assert rebuilt.history_for_cid(cid) == incremental.history_for_cid(cid)


def test_legacy_outcome_and_generic_reflection_do_not_join_an_episode() -> None:
    log = EventLog(":memory:")
    opening_assistant = _assistant(log, "COMMIT: legacy boundary")
    open_event_id = _open(
        log,
        cid="legacy",
        text="legacy boundary",
        assistant_id=opening_assistant,
    )
    legacy_outcome = log.append(
        kind="outcome_observation",
        content=json.dumps({"commitment_id": "legacy", "observed_result": "success"}),
        meta={"cid": "legacy"},
    )
    generic_reflection = log.append(
        kind="reflection",
        content="This resembles a later review.",
        meta={"cid": "legacy", "about_event": legacy_outcome},
    )

    graph = MemeGraph(log)
    graph.rebuild(log.read_all())
    episode = graph.episode_for_open(open_event_id)

    assert episode is not None
    assert episode.outcome_event_id is None
    assert episode.review_event_ids == ()
    assert legacy_outcome not in episode.event_ids
    assert generic_reflection not in episode.event_ids
    assert graph.cids_for_event(legacy_outcome) == []
    assert graph.cids_for_event(generic_reflection) == []
