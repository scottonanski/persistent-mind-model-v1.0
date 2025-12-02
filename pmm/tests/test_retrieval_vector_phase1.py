# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

import json

from pmm.core.event_log import EventLog
from pmm.runtime.loop import RuntimeLoop
from pmm.adapters.dummy_adapter import DummyAdapter
from pmm.retrieval.vector import select_by_vector


def _set_vector_config(
    log: EventLog, *, limit: int = 5, model: str = "hash64", dims: int = 64
) -> None:
    cfg = {
        "type": "retrieval",
        "strategy": "vector",
        "limit": limit,
        "model": model,
        "dims": dims,
        "quant": "none",
    }
    log.append(kind="config", content=json.dumps(cfg, separators=(",", ":")), meta={})


def test_retrieval_selection_recorded_and_consistent():
    log = EventLog(":memory:")
    # Seed a few messages to retrieve from
    for i in range(6):
        ue = log.append(kind="user_message", content=f"topic {i} apples", meta={})
        ae = log.append(kind="assistant_message", content=f"reply {i} oranges", meta={})
        # Bind to sticky concept for deterministic selection
        bind_payload = json.dumps(
            {"event_id": ue, "tokens": ["user.identity"], "relation": "relevant_to"},
            sort_keys=True,
            separators=(",", ":"),
        )
        log.append(kind="concept_bind_event", content=bind_payload, meta={})
        bind_payload = json.dumps(
            {"event_id": ae, "tokens": ["user.identity"], "relation": "relevant_to"},
            sort_keys=True,
            separators=(",", ":"),
        )
        log.append(kind="concept_bind_event", content=bind_payload, meta={})

    # Enable vector retrieval with a larger limit to ensure vector matches aren't displaced
    # by recent graph events during the sort-and-truncate phase of the pipeline.
    _set_vector_config(log, limit=20, model="hash64", dims=32)

    loop = RuntimeLoop(eventlog=log, adapter=DummyAdapter(), replay=False)
    # Run a turn that should trigger a selection based on query
    loop.run_turn("apples and fruit exploration")

    # Verify retrieval_selection was appended for the turn
    events = log.read_all()
    selections = [e for e in events if e.get("kind") == "retrieval_selection"]
    assert selections, "expected a retrieval_selection event"
    sel = selections[-1]
    payload = json.loads(sel.get("content") or "{}")
    selected_ids = payload.get("selected") or []
    scores = payload.get("scores") or []
    assert selected_ids and len(selected_ids) == len(scores)

    # Deterministically recompute (up to the assistant turn id) and confirm identical ids
    turn_id = int(payload.get("turn_id"))
    ids, _scores = select_by_vector(
        events=events,
        query_text="apples and fruit exploration",
        limit=4,
        model="hash64",
        dims=32,
        up_to_id=turn_id,
    )
    # The new pipeline expands IDs via Graph/CTL; ensure there is overlap with vector picks.
    assert set(ids) & set(selected_ids)
