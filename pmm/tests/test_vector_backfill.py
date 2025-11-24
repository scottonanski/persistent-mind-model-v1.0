# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

from pmm.core.event_log import EventLog
from pmm.runtime.indexer import Indexer


def test_backfill_embeddings_appends_missing_and_advances_cursor() -> None:
    log = EventLog(":memory:")
    # Two messages; only the first will get backfilled in a small batch
    ev1 = log.append(kind="user_message", content="hello world", meta={})
    log.append(kind="assistant_message", content="later text", meta={})

    indexer = Indexer(log)
    appended = indexer.backfill_embeddings(model="hash64", dims=16, batch=1)
    assert appended == 1

    # Should have an embedding_add for ev1
    emb_events = [
        e
        for e in log.read_by_kind("embedding_add")
        if e.get("meta", {}).get("source") == "indexer.backfill"
    ]
    assert len(emb_events) == 1
    content = emb_events[0]["content"]
    assert f'"event_id":{ev1}' in content

    # Cursor advanced; next call with batch=1 should process ev2
    appended2 = indexer.backfill_embeddings(model="hash64", dims=16, batch=1)
    assert appended2 == 1
    emb_events = [
        e
        for e in log.read_by_kind("embedding_add")
        if e.get("meta", {}).get("source") == "indexer.backfill"
    ]
    assert len(emb_events) == 2
