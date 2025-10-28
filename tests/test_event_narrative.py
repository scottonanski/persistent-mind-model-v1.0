from __future__ import annotations

import json
import sqlite3
from typing import Any

import pytest

from pmm.runtime.ledger.narrative import (
    EventNarrative,
    eventrow_to_narrative,
    get_event_narrative,
)


@pytest.fixture(name="mem_ledger")
def fixture_mem_ledger(tmp_path):
    """In-memory ledger stub providing get_event for narrative tests."""

    class Ledger:
        def __init__(self) -> None:
            self.conn = sqlite3.connect(":memory:")
            cur = self.conn.cursor()
            cur.execute(
                "CREATE TABLE events (id INTEGER PRIMARY KEY, kind TEXT, content TEXT, meta TEXT)"
            )
            cur.execute(
                "INSERT INTO events(id, kind, content, meta) VALUES (1, 'llm_latency', '', ?)",
                [
                    json.dumps(
                        {
                            "provider": "internal",
                            "model": "evalsum",
                            "op": "chat",
                            "ms": 0.35,
                            "tick": 30,
                        }
                    )
                ],
            )
            cur.execute(
                "INSERT INTO events(id, kind, content, meta) VALUES (2, 'identity_adopt', 'Echo', '{}')"
            )
            self.conn.commit()

        def get_event(self, event_id: int) -> dict[str, Any] | None:
            cur = self.conn.cursor()
            row = cur.execute(
                "SELECT id, kind, content, meta FROM events WHERE id = ?", (event_id,)
            ).fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "kind": row[1],
                "content": row[2],
                "meta": row[3],
            }

    return Ledger()


def test_get_event_narrative_meta_source(mem_ledger) -> None:
    narrative = get_event_narrative(mem_ledger, 1)
    assert isinstance(narrative, EventNarrative)
    assert narrative.source == "meta"
    assert narrative.confidence == "medium"
    assert "completed in" in narrative.text
    assert "evalsum" in narrative.text


def test_eventrow_to_narrative_content_path(mem_ledger) -> None:
    event = mem_ledger.get_event(2)
    assert event is not None
    narrative = eventrow_to_narrative(event)
    assert narrative.source == "content"
    assert narrative.confidence == "high"
    assert "Echo" in narrative.text
