from pmm.commitments.tracker import CommitmentTracker
from pmm.runtime.loop import emit_reflection
from pmm.storage.eventlog import EventLog


def test_reflection_opens_commitment(tmp_path):
    """Test that reflection-sourced commitments are created via tracker with proper metadata."""
    db = tmp_path / "ok.db"
    log = EventLog(str(db))
    tracker = CommitmentTracker(log)

    # Emit reflection (no longer creates commitment directly)
    rid = emit_reflection(
        log,
        "I realized I should improve consistency in my approach.\n"
        "Next, I'll track concrete next steps to ensure progress.",
    )

    # Simulate what Runtime.reflect() does: create commitment from extracted action
    tracker.add_commitment(
        text="Track concrete next steps to ensure progress",
        source="reflection",
        extra_meta={"reflection_id": rid},
    )

    evs = log.read_all()
    kinds = [e["kind"] for e in evs]
    assert "reflection" in kinds
    assert "reflection_check" in kinds
    assert "commitment_open" in kinds

    ref = next(e for e in evs if e["kind"] == "reflection")
    commit = next(e for e in evs if e["kind"] == "commitment_open")
    assert commit["meta"]["source"] == "reflection"  # Changed from "reason" to "source"
    assert commit["meta"]["reflection_id"] == ref["id"]


def test_empty_reflection_no_commitment(tmp_path):
    """Test that empty reflections don't create commitments (no action to extract)."""
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

    # Empty reflections should NOT create commitments (no actionable content to extract)
    commits = [e for e in evs if e["kind"] == "commitment_open"]
    assert len(commits) == 0  # No commitment should be created from empty reflection
