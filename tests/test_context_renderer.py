# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Tests for the context renderer."""

import json
from pmm.core.event_log import EventLog
from pmm.core.meme_graph import MemeGraph
from pmm.core.concept_graph import ConceptGraph
from pmm.core.mirror import Mirror
from pmm.retrieval.pipeline import RetrievalResult
from pmm.runtime.context_renderer import render_context


def test_render_context_full():
    """Test rendering a full context with all sections."""
    log = EventLog(":memory:")
    mg = MemeGraph(log)
    cg = ConceptGraph(log)
    mirror = Mirror(log)

    # 1. Concepts
    log.append(
        kind="concept_define",
        content=json.dumps(
            {
                "token": "topic.code",
                "concept_kind": "topic",
                "definition": "coding",
                "attributes": {},
                "version": "1",
            }
        ),
        meta={},
    )

    # 2. Threads
    cid = "thread-dev"
    e_asst = log.append(
        kind="assistant_message", content="I will code.\n\nCOMMIT: Code X", meta={}
    )
    e_open = log.append(
        kind="commitment_open", content="req", meta={"cid": cid, "text": "Code X"}
    )

    # Bind concept
    log.append(
        kind="concept_bind_event",
        content=json.dumps(
            {"event_id": e_open, "tokens": ["topic.code"], "relation": "relates_to"}
        ),
        meta={},
    )

    # 3. Identity (Mirror)
    log.append(
        kind="claim",
        content='identity={"new_name":"PMM"}',
        meta={"claim_type": "name_change"},
    )

    # 4. Evidence (Generic events)
    e_msg = log.append(kind="user_message", content="Do it", meta={})

    # Sync all
    events = log.read_all()
    mg.rebuild(events)
    cg.rebuild(events)
    mirror.rebuild(
        events
    )  # mirror might auto-sync if listen=True? verify Mirror class.
    # Mirror usually just reads log on demand or syncs.
    # In context_renderer we pass mirror instance.

    # Mock Result
    result = RetrievalResult(
        event_ids=[e_msg, e_asst, e_open],
        relevant_cids=[cid],
        active_concepts=["topic.code"],
    )

    ctx = render_context(
        result=result, eventlog=log, concept_graph=cg, meme_graph=mg, mirror=mirror
    )

    # Checks
    assert "## Concepts" in ctx
    assert "- topic.code: coding" in ctx

    assert "## Threads" in ctx
    assert f"- {cid}: Active - Code X [topic.code]" in ctx

    assert "Identity: name: PMM" in ctx
    assert f"Open Commitments: {cid}" in ctx

    assert "## Evidence" in ctx
    assert f"[{e_msg}] user_message: Do it" in ctx

    # Determinism check
    ctx2 = render_context(
        result=result, eventlog=log, concept_graph=cg, meme_graph=mg, mirror=mirror
    )
    assert ctx == ctx2
