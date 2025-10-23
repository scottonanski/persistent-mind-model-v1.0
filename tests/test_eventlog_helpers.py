from __future__ import annotations
from pmm.runtime.eventlog_helpers import append_once

class FakeEventLog:
    def __init__(self) -> None:
        self.events = []
    def read_tail(self, limit: int = 100) -> list[dict]:
        return self.events[-limit:]
    def append(self, kind: str, content: str, meta: dict | None = None) -> int:
        eid = len(self.events) + 1
        self.events.append({"id": eid, "kind": kind, "content": content, "meta": meta or {}})
        return eid

def test_append_once_dedupes_by_digest():
    log = FakeEventLog()
    key = {"traits": {"conscientiousness": 0.6}, "context": {"reason": "test"}}
    # first append happens
    ok1 = append_once(log, kind="identity_adjust_proposal", content="", meta={"source":"test"}, key=key, window=100)
    # second with same key is suppressed
    ok2 = append_once(log, kind="identity_adjust_proposal", content="", meta={"source":"test"}, key=key, window=100)
    assert ok1 is True and ok2 is False
    assert len(log.events) == 1
    # different key (changed target) should append
    key2 = {"traits": {"conscientiousness": 0.65}, "context": {"reason": "test"}}
    ok3 = append_once(log, kind="identity_adjust_proposal", content="", meta={"source":"test"}, key=key2, window=100)
    assert ok3 is True
    assert len(log.events) == 2
