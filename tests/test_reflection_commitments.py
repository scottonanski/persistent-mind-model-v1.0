from pmm.runtime.loop import emit_reflection
from pmm.storage.eventlog import EventLog


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
    assert isinstance(rid, int) and rid > 0
    evs = log.read_all()
    reflection = next(e for e in evs if e["kind"] == "reflection")
    assert reflection["id"] == rid
    # Runtime synthesizes fallback text for empty reflections; ensure it is recorded.
    assert reflection["content"].strip() != ""
    assert (reflection.get("meta") or {}).get("text", "").strip() != ""

    # Empty reflections now open a follow-up commitment once the quality check passes.
    commit = next(e for e in evs if e["kind"] == "commitment_open")
    assert commit["meta"]["reason"] == "reflection"
    assert commit["meta"]["ref"] == reflection["id"]
