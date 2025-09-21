from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import emit_reflection


def test_reflection_opens_commitment(tmp_path):
    db = tmp_path / "ok.db"
    log = EventLog(str(db))
    emit_reflection(
        log,
        "I realized I should improve consistency in my approach.\n"
        "Next, I'll track concrete next steps to ensure progress.",
    )
    evs = log.read_all()
    # reflection → reflection_check → commitment_open
    kinds = [e["kind"] for e in evs]
    assert "reflection" in kinds
    assert "reflection_check" in kinds
    assert "commitment_open" in kinds
    ref = next(e for e in evs if e["kind"] == "reflection")
    commit = next(e for e in evs if e["kind"] == "commitment_open")
    assert commit["meta"]["reason"] == "reflection"
    assert commit["meta"]["ref"] == ref["id"]


def test_empty_reflection_no_commitment(tmp_path):
    db = tmp_path / "empty.db"
    log = EventLog(str(db))
    rid = emit_reflection(log, "")
    assert rid is None  # authoritative acceptance rejects empty reflections
    evs = log.read_all()
    kinds = [e["kind"] for e in evs]
    # No reflection emitted when empty; ensure no commitment is opened
    assert "reflection" not in kinds
    assert "commitment_open" not in kinds
