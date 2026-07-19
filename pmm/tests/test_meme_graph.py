# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations


from pmm.core.event_log import EventLog
from pmm.core.event_log import TERMINAL_OUTCOME_PROTOCOL
from pmm.core.meme_graph import MemeGraph


def create_sample_events(log: EventLog) -> None:
    # Sample events for graph (canonical meta-based commitments)
    log.append(
        kind="user_message",
        content="hello",
        meta={"role": "user", "turn_protocol": TERMINAL_OUTCOME_PROTOCOL},
    )
    log.append(
        kind="assistant_message",
        content="COMMIT: task1 hi",
        meta={
            "role": "assistant",
            "turn_protocol": TERMINAL_OUTCOME_PROTOCOL,
            "about_event": 1,
        },
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
    assert meme_rebuild.prior_managed_pair(3) == meme_inc.prior_managed_pair(3)


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


def test_managed_reply_uses_canonical_about_event_not_latest_user():
    log = EventLog(":memory:")
    first_user = log.append(
        kind="user_message",
        content="first",
        meta={"role": "user", "turn_protocol": TERMINAL_OUTCOME_PROTOCOL},
    )
    latest_user = log.append(
        kind="user_message",
        content="interleaved",
        meta={"role": "user", "turn_protocol": TERMINAL_OUTCOME_PROTOCOL},
    )
    assistant, _ = log.append_terminal_outcome(
        user_event_id=first_user,
        kind="assistant_message",
        content="canonical reply",
        meta={"role": "assistant"},
    )

    meme = MemeGraph(log)
    meme.rebuild(log.read_all())

    assert meme.graph.has_edge(assistant, first_user)
    assert not meme.graph.has_edge(assistant, latest_user)
    assert meme.prior_managed_pair(assistant + 1) == (first_user, assistant)


def test_legacy_reply_fallback_is_not_promoted_to_managed_index():
    log = EventLog(":memory:")
    user_id = log.append(kind="user_message", content="legacy", meta={})
    assistant_id = log.append(
        kind="assistant_message",
        content="legacy reply",
        meta={"role": "assistant", "about_event": user_id},
    )

    meme = MemeGraph(log)
    meme.rebuild(log.read_all())

    assert meme.graph.has_edge(assistant_id, user_id)
    assert meme.prior_managed_pair(assistant_id + 1) is None


def test_invalid_managed_target_does_not_fall_back_to_latest_user():
    log = EventLog(":memory:")
    user_id = log.append(
        kind="user_message",
        content="managed",
        meta={"turn_protocol": TERMINAL_OUTCOME_PROTOCOL},
    )
    assistant_id = log.append(
        kind="assistant_message",
        content="invalid managed reply",
        meta={
            "turn_protocol": TERMINAL_OUTCOME_PROTOCOL,
            "about_event": 999999,
        },
    )

    meme = MemeGraph(log)
    meme.rebuild(log.read_all())

    assert not meme.graph.has_edge(assistant_id, user_id)
    assert meme.prior_managed_pair(assistant_id + 1) is None


def test_managed_pair_index_tolerates_out_of_order_assistant_delivery():
    protocol = TERMINAL_OUTCOME_PROTOCOL
    meme = MemeGraph(EventLog(":memory:"))
    meme.add_event(
        {"id": 1, "kind": "user_message", "meta": {"turn_protocol": protocol}}
    )
    meme.add_event(
        {"id": 3, "kind": "user_message", "meta": {"turn_protocol": protocol}}
    )
    meme.add_event(
        {
            "id": 4,
            "kind": "assistant_message",
            "meta": {"turn_protocol": protocol, "about_event": 3},
        }
    )
    meme.add_event(
        {
            "id": 2,
            "kind": "assistant_message",
            "meta": {"turn_protocol": protocol, "about_event": 1},
        }
    )

    assert meme._managed_assistant_ids == [2, 4]
    assert meme.prior_managed_pair(4) == (1, 2)
    assert meme.prior_managed_pair(5) == (3, 4)


def test_incomplete_and_failed_managed_turns_remain_outside_pair_index():
    log = EventLog(":memory:")
    completed_user = log.append(
        kind="user_message",
        content="complete",
        meta={"turn_protocol": TERMINAL_OUTCOME_PROTOCOL},
    )
    completed_assistant, _ = log.append_terminal_outcome(
        user_event_id=completed_user,
        kind="assistant_message",
        content="complete answer",
        meta={"role": "assistant"},
    )
    log.append(
        kind="user_message",
        content="incomplete",
        meta={"turn_protocol": TERMINAL_OUTCOME_PROTOCOL},
    )
    failed_user = log.append(
        kind="user_message",
        content="failed",
        meta={"turn_protocol": TERMINAL_OUTCOME_PROTOCOL},
    )
    log.append_terminal_outcome(
        user_event_id=failed_user,
        kind="generation_failure",
        content="diagnostic only",
        meta={"source": "runtime"},
    )
    current_user = log.append(
        kind="user_message",
        content="current",
        meta={"turn_protocol": TERMINAL_OUTCOME_PROTOCOL},
    )

    meme = MemeGraph(log)
    meme.rebuild(log.read_all())

    assert meme.prior_managed_pair(current_user) == (
        completed_user,
        completed_assistant,
    )


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
