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
        log.append(kind="user_message", content=f"topic {i} apples", meta={})
        log.append(kind="assistant_message", content=f"reply {i} oranges", meta={})

    # Enable vector retrieval
    _set_vector_config(log, limit=4, model="hash64", dims=32)

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
    assert ids == selected_ids
