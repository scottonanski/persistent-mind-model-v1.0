# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Tests for ConceptGraph <-> MemeGraph integration."""

import json
from pmm.core.event_log import EventLog
from pmm.core.meme_graph import MemeGraph
from pmm.core.concept_graph import ConceptGraph


def test_concept_thread_integration():
    """Test concepts_for_thread and threads_for_concept."""
    log = EventLog(":memory:")
    mg = MemeGraph(log)
    cg = ConceptGraph(log)

    # 1. Create a thread: Assistant -> Open -> Close
    cid = "thread-123"

    # Assistant Message (commits to)
    e_assistant = log.append(
        kind="assistant_message",
        content="I will do X.\n\nCOMMIT: I promise X",
        meta={},
    )

    # Commitment Open
    e_open = log.append(
        kind="commitment_open",
        content="User asks for X",
        meta={"cid": cid, "text": "I promise X"},
    )

    # Commitment Close
    e_close = log.append(
        kind="commitment_close",
        content="Task done",
        meta={"cid": cid},
    )

    # Rebuild/Sync graphs
    # Note: MemeGraph needs to see events to build edges.
    # We can call rebuild or add_event. Since we appended, we can just pass list.
    all_events = log.read_all()
    mg.rebuild(all_events)
    cg.rebuild(all_events)

    # Verify thread structure in MemeGraph
    thread_ids = mg.thread_for_cid(cid)
    assert e_open in thread_ids
    assert e_assistant in thread_ids
    assert e_close in thread_ids

    # 2. Define concepts
    log.append(
        kind="concept_define",
        content=json.dumps(
            {
                "token": "concept.planning",
                "concept_kind": "activity",
                "definition": "planning tasks",
                "attributes": {},
                "version": "1.0",
            }
        ),
        meta={},
    )
    log.append(
        kind="concept_define",
        content=json.dumps(
            {
                "token": "concept.execution",
                "concept_kind": "activity",
                "definition": "executing tasks",
                "attributes": {},
                "version": "1.0",
            }
        ),
        meta={},
    )

    # 3. Bind concepts to events
    # Bind planning to Open
    log.append(
        kind="concept_bind_event",
        content=json.dumps(
            {
                "event_id": e_open,
                "tokens": ["concept.planning"],
                "relation": "relates_to",
            }
        ),
        meta={},
    )
    # Bind execution to Assistant
    log.append(
        kind="concept_bind_event",
        content=json.dumps(
            {
                "event_id": e_assistant,
                "tokens": ["concept.execution"],
                "relation": "relates_to",
            }
        ),
        meta={},
    )

    # Update graphs again
    all_events = log.read_all()
    mg.rebuild(all_events)
    cg.rebuild(all_events)

    # 4. Test concepts_for_thread
    concepts = cg.concepts_for_thread(mg, cid)
    assert "concept.planning" in concepts
    assert "concept.execution" in concepts
    assert len(concepts) == 2

    # 5. Test threads_for_concept
    cids_planning = cg.threads_for_concept(mg, "concept.planning")
    assert cid in cids_planning
    assert len(cids_planning) == 1

    cids_execution = cg.threads_for_concept(mg, "concept.execution")
    assert cid in cids_execution
    assert len(cids_execution) == 1


def test_cids_for_event_logic():
    """Test MemeGraph.cids_for_event logic specifically."""
    log = EventLog(":memory:")
    mg = MemeGraph(log)

    cid = "test-cid"

    # Assistant (linked via commit text extraction logic in MemeGraph)
    e_assistant = log.append(
        kind="assistant_message",
        content="I will.\n\nCOMMIT: commit text",
        meta={},
    )

    # Open
    e_open = log.append(
        kind="commitment_open",
        content="req",
        meta={"cid": cid, "text": "commit text"},
    )

    # Close
    e_close = log.append(
        kind="commitment_close",
        content="done",
        meta={"cid": cid},
    )

    # Reflection (on assistant)
    e_reflection = log.append(
        kind="reflection",
        content="reflecting",
        meta={"about_event": e_assistant},
    )

    mg.rebuild(log.read_all())

    # Check graph edges first to ensure setup is correct
    # Open -> Assistant (commits_to)
    assert mg.graph.has_edge(e_open, e_assistant)
    assert mg.graph[e_open][e_assistant]["label"] == "commits_to"

    # Reflection -> Assistant (reflects_on)
    assert mg.graph.has_edge(e_reflection, e_assistant)
    assert mg.graph[e_reflection][e_assistant]["label"] == "reflects_on"

    # Check cids_for_event
    assert mg.cids_for_event(e_open) == [cid]
    assert mg.cids_for_event(e_close) == [cid]
    assert mg.cids_for_event(e_assistant) == [cid]
    assert mg.cids_for_event(e_reflection) == [cid]

    # Unrelated event
    e_unrelated = log.append(kind="user_message", content="hi", meta={})
    mg.add_event(log.get(e_unrelated))
    assert mg.cids_for_event(e_unrelated) == []
