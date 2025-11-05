from __future__ import annotations

import networkx as nx

from pmm_v2.core.event_log import EventLog
from pmm_v2.core.meme_graph import MemeGraph


def create_sample_events(log: EventLog) -> None:
    # Sample events for graph
    log.append(kind="user_message", content="hello", meta={"role": "user"})
    log.append(
        kind="assistant_message", content="COMMIT:task1 hi", meta={"role": "assistant"}
    )
    log.append(
        kind="commitment_open", content="COMMIT:task1", meta={"source": "assistant"}
    )
    log.append(
        kind="commitment_close", content="CLOSE:task1", meta={"source": "assistant"}
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

    # Compare using graph hash
    hash_rebuild = nx.weisfeiler_lehman_graph_hash(meme_rebuild.graph)
    hash_inc = nx.weisfeiler_lehman_graph_hash(meme_inc.graph)
    assert hash_rebuild == hash_inc


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
