import os
import tempfile

from pmm.storage.eventlog import EventLog
from pmm.commitments.tracker import open_violation_triage


def _new_db() -> str:
    fd, path = tempfile.mkstemp(prefix="pmm_triage_", suffix=".db")
    os.close(fd)
    return path


def test_violations_without_code_are_ignored():
    db = _new_db()
    log = EventLog(db)

    # Violations with missing/None code
    log.append(kind="invariant_violation", content="", meta={})
    log.append(kind="invariant_violation", content="", meta={"code": None})

    res = open_violation_triage(log.read_tail(limit=500), log)
    assert res == {"opened": [], "skipped": []}

    # Ensure no triage commitment was opened
    opens = [
        e
        for e in log.read_all()
        if e.get("kind") == "commitment_open"
        and (e.get("meta") or {}).get("reason") == "invariant_violation"
    ]
    assert opens == []
