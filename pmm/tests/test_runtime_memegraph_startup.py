from __future__ import annotations

import json
import os
import threading
from unittest.mock import patch

import pytest

from pmm.adapters.dummy_adapter import DummyAdapter
from pmm.core.event_log import EventLog
from pmm.core.meme_graph import MemeGraph
from pmm.runtime.loop import RuntimeLoop
from pmm.runtime.mcp_server import pmm_turn
from pmm.runtime.oneshot_cli import run_one_turn


class CaptureAdapter:
    def __init__(self, reply: str = "OK") -> None:
        self.reply = reply
        self.system_prompt = ""

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        self.system_prompt = system_prompt
        return self.reply


def _append_seed_history(log: EventLog) -> dict[str, int | str]:
    user_id = log.append(
        kind="user_message", content="seed user", meta={"role": "user"}
    )
    commitment_text = "restore the seeded commitment"
    assistant_id = log.append(
        kind="assistant_message",
        content=f"Seed response\nCOMMIT: {commitment_text}",
        meta={"role": "assistant"},
    )
    open_id = log.append(
        kind="commitment_open",
        content=f"Commitment opened: {commitment_text}",
        meta={
            "cid": "restore01",
            "origin": "assistant",
            "source": "assistant",
            "text": commitment_text,
        },
    )
    reflection_id = log.append(
        kind="reflection",
        content="seed reflection",
        meta={"about_event": assistant_id, "source": "test"},
    )
    close_id = log.append(
        kind="commitment_close",
        content="Commitment closed: restore01",
        meta={"cid": "restore01", "source": "assistant"},
    )
    log.append(
        kind="concept_define",
        content=json.dumps(
            {
                "token": "topic.restore",
                "concept_kind": "topic",
                "definition": "startup graph restoration",
                "attributes": {},
                "version": 1,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        meta={"source": "test"},
    )
    log.append(
        kind="concept_bind_thread",
        content=json.dumps(
            {
                "cid": "restore01",
                "tokens": ["topic.restore"],
                "relation": "relevant_to",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        meta={"source": "test"},
    )
    untracked_id = log.append(kind="test_event", content="not a graph node", meta={})
    return {
        "user": user_id,
        "assistant": assistant_id,
        "open": open_id,
        "reflection": reflection_id,
        "close": close_id,
        "untracked": untracked_id,
        "cid": "restore01",
    }


def _edges(graph: MemeGraph) -> list[tuple[int, int, str]]:
    return sorted(
        (int(source), int(target), str(data.get("label") or ""))
        for source, target, data in graph.graph.edges(data=True)
    )


def _selected_ids(result: dict) -> list[int]:
    selection = next(
        event for event in result["events"] if event["kind"] == "retrieval_selection"
    )
    return [int(event_id) for event_id in selection["content"]["selected"]]


def test_reopened_runtime_restores_live_graph_and_relationships(tmp_path) -> None:
    db_path = str(tmp_path / "continuity.db")
    live_log = EventLog(db_path)
    live = RuntimeLoop(eventlog=live_log, adapter=DummyAdapter(), autonomy=False)
    ids = _append_seed_history(live_log)

    live_nodes = sorted(int(node) for node in live.memegraph.graph.nodes)
    live_edges = _edges(live.memegraph)

    reopened_log = EventLog(db_path)
    reopened = RuntimeLoop(
        eventlog=reopened_log, adapter=DummyAdapter(), autonomy=False
    )

    assert sorted(int(node) for node in reopened.memegraph.graph.nodes) == live_nodes
    assert _edges(reopened.memegraph) == live_edges
    assert int(ids["untracked"]) not in reopened.memegraph.graph
    assert reopened.memegraph.graph[int(ids["close"])][int(ids["open"])][
        "label"
    ] == "closes"
    assert reopened.memegraph.graph[int(ids["reflection"])][int(ids["assistant"])][
        "label"
    ] == "reflects_on"
    assert reopened.memegraph.thread_for_cid(str(ids["cid"])) == [
        int(ids["assistant"]),
        int(ids["open"]),
        int(ids["close"]),
        int(ids["reflection"]),
    ]

    nodes_before_append = reopened.memegraph.graph.number_of_nodes()
    next_id = reopened_log.append(
        kind="user_message", content="post-rebuild", meta={"role": "user"}
    )
    reopened.memegraph.add_event(reopened_log.get(next_id))
    assert reopened.memegraph.graph.number_of_nodes() == nodes_before_append + 1


def test_graph_is_restored_before_first_retrieval(tmp_path) -> None:
    db_path = str(tmp_path / "first-retrieval.db")
    seed_log = EventLog(db_path)
    ids = _append_seed_history(seed_log)
    adapter = CaptureAdapter()

    from pmm.runtime import loop as loop_module

    production_retrieval = loop_module.run_retrieval_pipeline

    def assert_restored_before_retrieval(**kwargs):
        graph = kwargs["meme_graph"]
        assert graph.graph.has_edge(int(ids["close"]), int(ids["open"]))
        assert graph.graph.has_edge(int(ids["reflection"]), int(ids["assistant"]))
        return production_retrieval(**kwargs)

    runtime = RuntimeLoop(
        eventlog=EventLog(db_path), adapter=adapter, autonomy=False
    )
    with patch.object(
        loop_module,
        "run_retrieval_pipeline",
        side_effect=assert_restored_before_retrieval,
    ):
        runtime.run_turn("Use topic.restore")

    assert "restore the seeded commitment" in adapter.system_prompt


def test_rebuild_listener_handoff_captures_concurrent_append() -> None:
    log = EventLog(":memory:")
    first_id = log.append(
        kind="user_message", content="before", meta={"role": "user"}
    )
    graph = MemeGraph(log)
    rebuild_started = threading.Event()
    release_rebuild = threading.Event()
    incrementally_delivered: list[int] = []

    def blocked_rebuild(events):
        rebuild_started.set()
        assert release_rebuild.wait(timeout=2)
        graph.rebuild(
            [event for event in events if event.get("kind") in graph.TRACKED_KINDS]
        )

    def incremental_listener(event):
        incrementally_delivered.append(int(event["id"]))
        graph.add_event(event)

    bootstrap = threading.Thread(
        target=lambda: log.rebuild_and_register_listener(
            blocked_rebuild, incremental_listener
        )
    )
    bootstrap.start()
    assert rebuild_started.wait(timeout=2)

    appended: list[int] = []
    append_thread = threading.Thread(
        target=lambda: appended.append(
            log.append(
                kind="assistant_message",
                content="after",
                meta={"role": "assistant"},
            )
        )
    )
    append_thread.start()
    assert append_thread.is_alive()

    release_rebuild.set()
    bootstrap.join(timeout=2)
    append_thread.join(timeout=2)

    assert not bootstrap.is_alive()
    assert not append_thread.is_alive()
    assert sorted(int(node) for node in graph.graph.nodes) == [first_id, appended[0]]
    assert graph.graph[appended[0]][first_id]["label"] == "replies_to"
    assert incrementally_delivered == [appended[0]]

    # Simulate a delayed emission for an event already included in replay.
    log._emit(log.get(first_id))
    assert incrementally_delivered == [appended[0]]


def test_rebuild_failure_aborts_runtime_before_services_start(tmp_path) -> None:
    db_path = str(tmp_path / "failed-rebuild.db")
    log = EventLog(db_path)
    log.append(kind="user_message", content="seed", meta={"role": "user"})

    with patch.object(MemeGraph, "rebuild", side_effect=RuntimeError("rebuild failed")):
        with pytest.raises(RuntimeError, match="rebuild failed"):
            RuntimeLoop(eventlog=log, adapter=DummyAdapter(), autonomy=False)

    assert log.read_by_kind("autonomy_rule_table") == []


def test_replay_restores_without_mutating_hash_chain_and_listens_incrementally(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "replay.db")
    seed_log = EventLog(db_path)
    RuntimeLoop(eventlog=seed_log, adapter=DummyAdapter(), autonomy=False)
    ids = _append_seed_history(seed_log)
    hashes_before = [event["hash"] for event in seed_log.read_all()]

    replay_log = EventLog(db_path)
    runtime = RuntimeLoop(
        eventlog=replay_log, adapter=DummyAdapter(), replay=True, autonomy=False
    )

    assert [event["hash"] for event in replay_log.read_all()] == hashes_before
    assert runtime.memegraph.graph.has_edge(int(ids["close"]), int(ids["open"]))
    nodes_before = runtime.memegraph.graph.number_of_nodes()
    replay_log.append(
        kind="user_message", content="replay incremental", meta={"role": "user"}
    )
    assert runtime.memegraph.graph.number_of_nodes() == nodes_before + 1


def test_consecutive_one_shot_invocations_restore_history(tmp_path) -> None:
    db_path = str(tmp_path / "oneshot.db")
    ids = _append_seed_history(EventLog(db_path))

    first_adapter = CaptureAdapter()
    first = run_one_turn(
        db_path=db_path,
        prompt="Use topic.restore",
        adapter=first_adapter,
        include_events=True,
    )
    second_adapter = CaptureAdapter()
    second = run_one_turn(
        db_path=db_path,
        prompt="Use topic.restore again",
        adapter=second_adapter,
        include_events=True,
    )

    required = {int(ids["assistant"]), int(ids["open"]), int(ids["close"])}
    assert required.issubset(_selected_ids(first))
    assert required.issubset(_selected_ids(second))
    assert "restore the seeded commitment" in first_adapter.system_prompt
    assert "restore the seeded commitment" in second_adapter.system_prompt


def test_consecutive_mcp_invocations_restore_history(tmp_path) -> None:
    db_path = str(tmp_path / "mcp.db")
    ids = _append_seed_history(EventLog(db_path))

    with patch.dict(os.environ, {"PMM_MCP_DB": db_path}):
        first = pmm_turn(
            prompt="Use topic.restore", model="dummy:", include_events=True
        )
        second = pmm_turn(
            prompt="Use topic.restore again", model="dummy:", include_events=True
        )

    required = {int(ids["assistant"]), int(ids["open"]), int(ids["close"])}
    assert required.issubset(_selected_ids(first))
    assert required.issubset(_selected_ids(second))
