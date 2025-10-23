from __future__ import annotations
from pmm.runtime.eventlog_helpers import append_once


class FakeEventLog:
    def __init__(self):
        self.events = []

    def read_tail(self, limit: int = 100):
        return self.events[-limit:]

    def append(self, kind: str, content: str, meta: dict | None = None):
        eid = len(self.events) + 1
        self.events.append({
            "id": eid,
            "kind": kind,
            "content": content,
            "meta": meta or {},
        })
        return eid


def test_append_once_digest_order_insensitive():
    log = FakeEventLog()
    k1 = {
        "traits": {"conscientiousness": 0.6, "openness": 0.4},
        "context": {"a": 1, "b": 2},
    }
    k2 = {
        "context": {"b": 2, "a": 1},
        "traits": {"openness": 0.4, "conscientiousness": 0.6},
    }
    ok1 = append_once(
        log,
        kind="identity_adjust_proposal",
        content="",
        meta={"source": "t"},
        key=k1,
        window=100,
    )
    ok2 = append_once(
        log,
        kind="identity_adjust_proposal",
        content="",
        meta={"source": "t"},
        key=k2,
        window=100,
    )
    assert ok1 is True and ok2 is False
    assert len(log.events) == 1
