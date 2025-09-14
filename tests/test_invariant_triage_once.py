import os
import tempfile

from pmm.storage.eventlog import EventLog
from pmm.commitments.tracker import (
    open_violation_triage,
    TRIAGE_TEXT_TMPL,
    TRIAGE_PRIORITY,
)


def _new_db() -> str:
    fd, path = tempfile.mkstemp(prefix="pmm_triage_", suffix=".db")
    os.close(fd)
    return path


def _get_open_triage_event(log: EventLog):
    for e in log.read_all():
        if e.get("kind") == "commitment_open":
            m = e.get("meta") or {}
            if (m.get("reason") == "invariant_violation") and (
                m.get("code") is not None
            ):
                return e
    return None


def test_triage_opens_once_per_code_and_is_idempotent():
    db = _new_db()
    log = EventLog(db)

    # seed two violations with the same code
    log.append(kind="invariant_violation", content="", meta={"code": "X1"})
    log.append(kind="invariant_violation", content="", meta={"code": "X1"})

    # first pass should open exactly one triage
    res1 = open_violation_triage(log.read_tail(limit=500), log)
    assert res1 == {"opened": ["X1"], "skipped": []}

    # second pass should be no-op
    res2 = open_violation_triage(log.read_tail(limit=500), log)
    assert res2 == {"opened": [], "skipped": ["X1"]}

    # verify event fields
    ev_open = _get_open_triage_event(log)
    assert ev_open is not None
    meta = ev_open.get("meta") or {}
    assert meta.get("priority") == TRIAGE_PRIORITY
    assert meta.get("reason") == "invariant_violation"
    assert meta.get("code") == "X1"
    assert meta.get("text") == TRIAGE_TEXT_TMPL.format(code="X1")
    # content is a descriptive wrapper from CommitmentTracker.add_commitment
    assert ev_open.get("content", "").startswith("Commitment opened:")

    # Close flow: append a commitment_close with the same cid; re-call triage → no reopen in-window
    cid = str(meta.get("cid"))
    assert cid
    log.append(
        kind="commitment_close",
        content=f"Commitment closed: {cid}",
        meta={"cid": cid, "evidence_type": "done", "description": "triage handled"},
    )
    res3 = open_violation_triage(log.read_tail(limit=500), log)
    assert res3 == {"opened": [], "skipped": ["X1"]}

    # New code should open exactly one triage
    log.append(kind="invariant_violation", content="", meta={"code": "X2"})
    res4 = open_violation_triage(log.read_tail(limit=500), log)
    assert res4 == {"opened": ["X2"], "skipped": ["X1"]}
