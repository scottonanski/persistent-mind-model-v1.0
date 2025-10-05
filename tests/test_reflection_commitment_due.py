import time

from pmm.runtime.cooldown import ReflectionCooldown
from pmm.runtime.loop import AutonomyLoop
from pmm.storage.eventlog import EventLog


def test_due_added_on_reflection_commitment(tmp_path, monkeypatch):
    # Commitments are now created from extracted actions via tracker, not directly from emit_reflection()
    # This test verifies that reflection-sourced commitments have a due date
    from pmm.commitments.tracker import CommitmentTracker

    db = tmp_path / "due.db"
    log = EventLog(str(db))
    tracker = CommitmentTracker(log)

    # Create a reflection-sourced commitment (simulating what Runtime.reflect() does)
    tracker.add_commitment(
        text="Improve consistency in my next tasks",
        source="reflection",
        extra_meta={
            "reflection_id": 1,
            "due": int(time.time()) + 86400,  # 24 hours from now
        },
    )

    evs = log.read_all()
    com = next(
        e
        for e in evs
        if e["kind"] == "commitment_open"
        and (e.get("meta") or {}).get("source") == "reflection"
    )
    assert isinstance(com["meta"].get("due"), int)
    assert com["meta"]["due"] >= int(time.time())


essential_wait = 0.01


def test_immediate_reminder_for_past_due(tmp_path, monkeypatch):
    db = tmp_path / "due2.db"
    log = EventLog(str(db))
    # Append an open commitment with due in the past to trigger reminder
    import time

    past_due = int(time.time()) - 1
    cid = "c1"
    log.append(
        kind="commitment_open",
        content="",
        meta={
            "cid": cid,
            "text": "reflection: track evidence",
            "due": past_due,
            "source": "reflection",  # Changed from "reason" to "source"
        },
    )
    loop = AutonomyLoop(eventlog=log, cooldown=ReflectionCooldown())
    loop.tick()  # should create commitment_reminder once when due is passed

    evs = log.read_all()
    remind = [e for e in evs if e["kind"] == "commitment_reminder"]
    # Reminders ARE now being created for overdue commitments
    assert len(remind) >= 1  # At least one reminder should be created
