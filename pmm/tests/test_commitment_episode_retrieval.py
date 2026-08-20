# SPDX-License-Identifier: PMM-1.0

from __future__ import annotations

import json

from pmm.core.commitment_manager import CommitmentManager
from pmm.core.concept_graph import ConceptGraph
from pmm.core.event_log import EventLog
from pmm.core.meme_graph import MemeGraph
from pmm.core.mirror import Mirror
from pmm.retrieval.pipeline import RetrievalConfig, run_retrieval_pipeline
from pmm.runtime.context_renderer import render_context


def _assistant(log: EventLog, content: str) -> int:
    return log.append(
        kind="assistant_message",
        content=content,
        meta={"role": "assistant"},
    )


def _open_episode(log: EventLog, text: str) -> tuple[str, int, int]:
    assistant_id = _assistant(log, f"COMMIT: {text}")
    cid, created = CommitmentManager(log).open_commitment_status(
        text,
        origin_event_id=assistant_id,
    )
    assert created
    open_event = CommitmentManager(log).get_open_commitments()[0]
    return cid, assistant_id, int(open_event["id"])


def _close_episode(log: EventLog, cid: str) -> tuple[int, int]:
    assistant_id = _assistant(log, f"CLOSE: {cid}")
    close_id, created = CommitmentManager(log).close_commitment_status(
        cid,
        origin_event_id=assistant_id,
    )
    assert created and close_id is not None
    return assistant_id, close_id


def _bind_event(log: EventLog, event_id: int, token: str) -> None:
    log.append(
        kind="concept_bind_event",
        content=json.dumps(
            {
                "event_id": event_id,
                "tokens": [token],
                "relation": "relates_to",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        meta={"source": "test_fixture"},
    )


def _bind_thread(log: EventLog, cid: str, token: str) -> None:
    log.append(
        kind="concept_bind_thread",
        content=json.dumps(
            {"cid": cid, "tokens": [token], "relation": "relates_to"},
            sort_keys=True,
            separators=(",", ":"),
        ),
        meta={"source": "test_fixture"},
    )


def _graphs(log: EventLog) -> tuple[MemeGraph, MemeGraph, ConceptGraph]:
    events = log.read_all()
    rebuilt = MemeGraph(log)
    rebuilt.rebuild(events)
    incremental = MemeGraph(log)
    for event in events:
        incremental.add_event(event)
    concepts = ConceptGraph(log)
    concepts.rebuild(events)
    return rebuilt, incremental, concepts


def _retrieve(
    log: EventLog,
    graph: MemeGraph,
    concepts: ConceptGraph,
    token: str,
    **config_overrides: int,
):
    return run_retrieval_pipeline(
        query_text="",
        eventlog=log,
        concept_graph=concepts,
        meme_graph=graph,
        config=RetrievalConfig(
            always_include_concepts=[token],
            sticky_concepts=[],
            include_summary_events=False,
            enable_vector_search=False,
            **config_overrides,
        ),
    )


def test_selected_historical_event_adds_exact_episode_and_current_episode() -> None:
    log = EventLog(":memory:")
    cid, first_assistant, first_open = _open_episode(log, "repeatable task")
    closing_assistant, first_close = _close_episode(log, cid)
    _, current_assistant, current_open = _open_episode(log, "repeatable task")
    _bind_event(log, first_open, "topic.history")

    rebuilt, incremental, concepts = _graphs(log)
    rebuilt_result = _retrieve(log, rebuilt, concepts, "topic.history")
    incremental_result = _retrieve(log, incremental, concepts, "topic.history")

    assert rebuilt_result == incremental_result
    result = rebuilt_result
    assert result.episode_selections == {
        first_open: {
            "cid": cid,
            "role": "historical",
            "trigger_event_ids": [first_open],
        },
        current_open: {
            "cid": cid,
            "role": "current",
            "trigger_event_ids": [],
        },
    }
    assert {
        first_assistant,
        first_open,
        closing_assistant,
        first_close,
        current_assistant,
        current_open,
    }.issubset(result.event_ids)
    assert (
        "historical_episode_expansion" in result.provenance[first_assistant]["reasons"]
    )
    assert result.provenance[first_open]["episodes"] == [
        {
            "cid": cid,
            "open_event_id": first_open,
            "role": "historical",
            "trigger_event_ids": [first_open],
        }
    ]
    assert "thread_expansion" in result.provenance[current_assistant]["reasons"]

    rendered = render_context(
        result=result,
        eventlog=log,
        concept_graph=concepts,
        meme_graph=rebuilt,
        mirror=Mirror(log),
    )
    assert f"Current episode (open event {current_open}): Active" in rendered
    assert f"Historical episode (open event {first_open}): Closed" in rendered
    assert f"episode={cid}/open-{first_open}/historical" in rendered


def test_cid_binding_selects_current_episode_without_dragging_closed_history() -> None:
    log = EventLog(":memory:")
    cid, first_assistant, first_open = _open_episode(log, "repeatable task")
    _, first_close = _close_episode(log, cid)
    _, current_assistant, current_open = _open_episode(log, "repeatable task")
    _bind_thread(log, cid, "topic.current")

    rebuilt, _, concepts = _graphs(log)
    result = _retrieve(log, rebuilt, concepts, "topic.current")

    assert result.episode_selections == {
        current_open: {
            "cid": cid,
            "role": "current",
            "trigger_event_ids": [],
        }
    }
    assert current_assistant in result.event_ids
    assert current_open in result.event_ids
    assert first_assistant not in result.event_ids
    assert first_open not in result.event_ids
    assert first_close not in result.event_ids


def test_current_subgraph_does_not_drag_another_episode_through_shared_assistant() -> (
    None
):
    log = EventLog(":memory:")
    assistant_id = _assistant(log, "COMMIT: first task\nCOMMIT: second task")
    first_cid, first_created = CommitmentManager(log).open_commitment_status(
        "first task",
        origin_event_id=assistant_id,
    )
    second_cid, second_created = CommitmentManager(log).open_commitment_status(
        "second task",
        origin_event_id=assistant_id,
    )
    assert first_created and second_created
    opens = {
        (event.get("meta") or {}).get("cid"): int(event["id"])
        for event in CommitmentManager(log).get_open_commitments()
    }
    _bind_thread(log, first_cid, "topic.shared")

    rebuilt, _, concepts = _graphs(log)
    result = _retrieve(log, rebuilt, concepts, "topic.shared")

    assert result.relevant_cids == [first_cid]
    assert set(result.episode_selections) == {opens[first_cid]}
    assert assistant_id in result.event_ids
    assert opens[first_cid] in result.event_ids
    assert opens[second_cid] not in result.event_ids


def test_historical_episode_count_and_event_expansion_are_bounded() -> None:
    log = EventLog(":memory:")
    cid, first_assistant, first_open = _open_episode(log, "repeatable task")
    _, first_close = _close_episode(log, cid)
    _, _, second_open = _open_episode(log, "repeatable task")
    _close_episode(log, cid)
    _, _, current_open = _open_episode(log, "repeatable task")
    _bind_event(log, first_open, "topic.bounded")
    _bind_event(log, second_open, "topic.bounded")

    rebuilt, _, concepts = _graphs(log)
    result = _retrieve(
        log,
        rebuilt,
        concepts,
        "topic.bounded",
        historical_episode_limit=1,
        historical_episode_event_limit=1,
    )

    assert set(result.episode_selections) == {second_open, current_open}
    assert first_open in result.event_ids  # independently selected concept evidence
    assert first_assistant not in result.event_ids
    assert first_close not in result.event_ids
    historical_expansion = {
        event_id
        for event_id, item in result.provenance.items()
        if "historical_episode_expansion" in item["reasons"]
    }
    assert len(historical_expansion) == 1
