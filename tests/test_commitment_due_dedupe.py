from __future__ import annotations
from pmm.runtime.eventlog_helpers import append_once

class FakeEventLog:
    def __init__(self): self.events=[]
    def read_tail(self, limit: int = 500): return self.events[-limit:]
    def append(self, kind: str, content: str, meta: dict | None=None):
        eid=len(self.events)+1; self.events.append({"id":eid,"kind":kind,"content":content,"meta":meta or {}}); return eid

def emit_commitment_due(log, cid: str, due_epoch: int):
    # mirrors loop.py usage (lazy import there; direct call here)
    key={"cid": str(cid), "due_epoch": int(due_epoch)}
    append_once(log, kind="commitment_due", content="", meta=key, key=key, window=500)

def test_commitment_due_dedupes_on_cid_and_due_epoch():
    log=FakeEventLog()
    emit_commitment_due(log, "c1", 123456)
    emit_commitment_due(log, "c1", 123456)  # duplicate → suppressed
    emit_commitment_due(log, "c1", 123457)  # new due → allowed
    emit_commitment_due(log, "c2", 123456)  # different cid → allowed
    kinds=[(e["kind"], e["meta"].get("cid"), e["meta"].get("due_epoch")) for e in log.events]
    assert kinds == [
        ("commitment_due","c1",123456),
        ("commitment_due","c1",123457),
        ("commitment_due","c2",123456),
    ]
    assert len(log.events) == 3
