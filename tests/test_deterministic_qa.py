from __future__ import annotations

import json
import sqlite3
from typing import Any

import pytest

from pmm.runtime.qa.deterministic import try_answer_event_question


@pytest.fixture(name="ledger_stub")
def fixture_ledger_stub():
    class Ledger:
        def __init__(self) -> None:
            self.conn = sqlite3.connect(":memory:")
            cur = self.conn.cursor()
            cur.execute(
                "CREATE TABLE events (id INTEGER PRIMARY KEY, kind TEXT, content TEXT, meta TEXT)"
            )
            cur.execute(
                "INSERT INTO events(id, kind, content, meta) VALUES (333, 'llm_latency', '', ?)",
                [
                    json.dumps(
                        {
                            "provider": "internal",
                            "model": "evalsum",
                            "op": "chat",
                            "ms": 0.25,
                            "tick": 42,
                        }
                    )
                ],
            )
            self.conn.commit()

        def get_event(self, event_id: int) -> dict[str, Any] | None:
            cur = self.conn.cursor()
            row = cur.execute(
                "SELECT id, kind, content, meta FROM events WHERE id = ?", (event_id,)
            ).fetchone()
            if not row:
                return None
            return {"id": row[0], "kind": row[1], "content": row[2], "meta": row[3]}

    return Ledger()


def test_try_answer_event_question_success(ledger_stub) -> None:
    answer = try_answer_event_question(ledger_stub, "What was event #333?")
    assert answer is not None
    assert "Event #333" in answer
    assert "internal::evalsum" in answer
    assert "tick 42" in answer


def test_try_answer_event_question_non_event(ledger_stub) -> None:
    answer = try_answer_event_question(ledger_stub, "How are you today?")
    assert answer is None
