from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import emit_reflection


def test_reflection_check_ok(tmp_path):
    db_path = tmp_path / "ok.db"
    log = EventLog(str(db_path))
    text = "I realized X.\nNext, I'll try Y."
    rid = emit_reflection(log, text)
    events = log.read_all()
    # Find the reflection by id
    ref = next(e for e in events if e["id"] == rid and e["kind"] == "reflection")
    # The next event must be reflection_check and must reference the reflection id
    idx = events.index(ref)
    assert idx + 1 < len(events)
    check = events[idx + 1]
    assert check["kind"] == "reflection_check"
    meta = check.get("meta") or {}
    assert meta.get("ref") == rid
    assert meta.get("ok") is True
    assert meta.get("reason") == "last_line_nonempty"


def test_reflection_check_empty(tmp_path):
    db_path = tmp_path / "empty.db"
    log = EventLog(str(db_path))
    rid = emit_reflection(log, "")
    events = log.read_all()
    ref = next(e for e in events if e["id"] == rid and e["kind"] == "reflection")
    idx = events.index(ref)
    check = events[idx + 1]
    assert check["kind"] == "reflection_check"
    meta = check.get("meta") or {}
    assert meta.get("ref") == rid
    assert meta.get("ok") is False
    assert meta.get("reason") == "empty_reflection"


def test_reflection_check_trailing_blank(tmp_path):
    db_path = tmp_path / "trail.db"
    log = EventLog(str(db_path))
    rid = emit_reflection(log, "Insight...\n\n")
    events = log.read_all()
    ref = next(e for e in events if e["id"] == rid and e["kind"] == "reflection")
    idx = events.index(ref)
    check = events[idx + 1]
    assert check["kind"] == "reflection_check"
    meta = check.get("meta") or {}
    assert meta.get("ref") == rid
    assert meta.get("ok") is False
    assert meta.get("reason") == "no_final_line"
