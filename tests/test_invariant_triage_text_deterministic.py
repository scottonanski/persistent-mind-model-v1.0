import os
import tempfile

from pmm.storage.eventlog import EventLog
from pmm.commitments.tracker import open_violation_triage, TRIAGE_TEXT_TMPL


def _new_db() -> str:
    fd, path = tempfile.mkstemp(prefix="pmm_triage_", suffix=".db")
    os.close(fd)
    return path


def test_triage_text_is_exact_and_sorted_by_code():
    db = _new_db()
    log = EventLog(db)

    # Seed out of order to verify sorted emission
    for code in ["B2", "A1", "C3"]:
        log.append(kind="invariant_violation", content="", meta={"code": code})

    open_violation_triage(log.read_tail(limit=500), log)

    texts = [
        (e.get("meta") or {}).get("text")
        for e in log.read_all()
        if e.get("kind") == "commitment_open"
        and (e.get("meta") or {}).get("reason") == "invariant_violation"
    ]
    assert texts == [
        TRIAGE_TEXT_TMPL.format(code="A1"),
        TRIAGE_TEXT_TMPL.format(code="B2"),
        TRIAGE_TEXT_TMPL.format(code="C3"),
    ]
