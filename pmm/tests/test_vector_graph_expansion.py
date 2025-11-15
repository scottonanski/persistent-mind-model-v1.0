# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

from pmm.core.event_log import EventLog
from pmm.retrieval.vector import expand_ids_via_graph
from pmm.core.meme_graph import MemeGraph


def _make_graph_events(log: EventLog) -> None:
    # user (1) -> assistant (2) -> commitment_open (3) -> commitment_close (4)
    log.append(kind="user_message", content="hello", meta={"role": "user"})
    log.append(
        kind="assistant_message", content="COMMIT: task1 hi", meta={"role": "assistant"}
    )
    log.append(
        kind="commitment_open",
        content="Commitment opened: task1 hi",
        meta={"source": "assistant", "cid": "task1", "text": "task1 hi"},
    )
    log.append(
        kind="commitment_close",
        content="Commitment closed: task1",
        meta={"source": "assistant", "cid": "task1"},
    )


def test_expand_ids_via_graph_includes_neighbors() -> None:
    log = EventLog(":memory:")
    _make_graph_events(log)
    events = log.read_all()

    # Sanity: MemeGraph builds expected structure
    mg = MemeGraph(log)
    mg.rebuild(events)
    neigh = mg.neighbors(2, direction="both")
    assert set(neigh) == {1, 3}

    expanded = expand_ids_via_graph(
        base_ids=[2],
        events=events,
        eventlog=log,
        max_expanded=10,
    )

    # Expanded ids should include base id and its neighbors
    assert 2 in expanded
    assert 1 in expanded
    assert 3 in expanded
    # Deterministic ordering
    assert expanded == sorted(expanded)
