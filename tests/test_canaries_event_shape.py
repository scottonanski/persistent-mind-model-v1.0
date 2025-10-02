import os
import tempfile

from pmm.runtime.canaries import run_canaries
from pmm.storage.eventlog import EventLog


def _tmpdb():
    fd, path = tempfile.mkstemp(prefix="pmm_canary_", suffix=".db")
    os.close(fd)
    return path


def test_canary_result_events_written():
    db = _tmpdb()
    log = EventLog(db)

    def chat(p: str) -> str:
        if "12 + 7" in p:
            return "19"
        if "pi" in p:
            return "3.142"
        return "2025-09-13"

    for r in run_canaries(chat):
        log.append(
            kind="canary_result",
            content="",
            meta={"name": r["name"], "pass": r["passed"]},
        )

    evs = [e for e in log.read_all() if e["kind"] == "canary_result"]
    assert len(evs) == 3
    assert all(
        "name" in (e.get("meta") or {}) and "pass" in (e.get("meta") or {}) for e in evs
    )
