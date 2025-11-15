# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations


from pmm.core.event_log import EventLog
from pmm.core.meme_graph import MemeGraph


def create_sample_events(log: EventLog) -> None:
    # Sample events for graph (canonical meta-based commitments)
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
    log.append(
        kind="reflection", content="reflect", meta={"about_event": 2}
    )  # about assistant_message


def test_rebuild_equals_incremental():
    log = EventLog(":memory:")
    create_sample_events(log)

    # Rebuild
    meme_rebuild = MemeGraph(log)
    meme_rebuild.rebuild(log.read_all())

    # Incremental
    meme_inc = MemeGraph(log)
    events = log.read_all()
    for event in events:
        meme_inc.add_event(event)

    # Compare deterministically via canonicalized edge set (u,v,label)
    def _canon_edges(G):
        return sorted((u, v, (d.get("label") or "")) for u, v, d in G.edges(data=True))

    assert _canon_edges(meme_rebuild.graph) == _canon_edges(meme_inc.graph)


def test_edges_correctly_built():
    log = EventLog(":memory:")
    create_sample_events(log)

    meme = MemeGraph(log)
    meme.rebuild(log.read_all())

    # Check edges
    # assistant_message (id=2) replies_to user_message (id=1)
    assert meme.graph.has_edge(2, 1)
    assert meme.graph[2][1]["label"] == "replies_to"

    # commitment_open (id=3) commits_to assistant_message (id=2)
    assert meme.graph.has_edge(3, 2)
    assert meme.graph[3][2]["label"] == "commits_to"

    # commitment_close (id=4) closes commitment_open (id=3)
    assert meme.graph.has_edge(4, 3)
    assert meme.graph[4][3]["label"] == "closes"

    # reflection (id=5) reflects_on assistant_message (id=2)
    assert meme.graph.has_edge(5, 2)
    assert meme.graph[5][2]["label"] == "reflects_on"


def test_add_event_idempotent():
    log = EventLog(":memory:")
    log.append(kind="user_message", content="hello", meta={"role": "user"})

    meme = MemeGraph(log)
    event = log.read_all()[0]

    # Add twice
    meme.add_event(event)
    nodes1 = list(meme.graph.nodes)
    edges1 = list(meme.graph.edges)

    meme.add_event(event)
    nodes2 = list(meme.graph.nodes)
    edges2 = list(meme.graph.edges)

    assert nodes1 == nodes2
    assert edges1 == edges2


def test_neighbors_subgraph_and_frontier():
    log = EventLog(":memory:")
    create_sample_events(log)

    meme = MemeGraph(log)
    meme.rebuild(log.read_all())

    # Neighbors around assistant_message (id=2)
    neigh_both = meme.neighbors(2, direction="both")
    # Expect links to user (1), commitment_open (3), reflection (5)
    assert set(neigh_both) == {1, 3, 5}

    # Neighbors filtered by kind
    neigh_reflections = meme.neighbors(2, direction="both", kind="reflection")
    assert neigh_reflections == [5]

    # Subgraph for commitment cid
    sub = meme.subgraph_for_cid("task1")
    thread = meme.thread_for_cid("task1")
    for eid in thread:
        assert eid in sub

    # Frontier should select recent nodes but return sorted ids
    frontier = meme.recent_frontier(limit=3)
    assert len(frontier) == 3
    assert frontier == sorted(frontier)
