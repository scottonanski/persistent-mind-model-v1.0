import time
from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import emit_reflection, AutonomyLoop
from pmm.runtime.cooldown import ReflectionCooldown


def test_due_added_on_reflection_commitment(tmp_path, monkeypatch):
    # Ensure default hours (24); also allow negative clamp behavior not to interfere
    monkeypatch.delenv("PMM_REFLECTION_COMMIT_DUE_HOURS", raising=False)
    db = tmp_path / "due.db"
    log = EventLog(str(db))
    # Emit a non-empty reflection through helper (which also appends reflection_check)
    emit_reflection(log, "I will improve consistency.")

    evs = log.read_all()
    com = next(
        e
        for e in evs
        if e["kind"] == "commitment_open"
        and (e.get("meta") or {}).get("reason") == "reflection"
    )
    assert isinstance(com["meta"].get("due"), int)
    assert com["meta"]["due"] >= int(time.time())


essential_wait = 0.01


def test_immediate_reminder_when_zero_hours(tmp_path, monkeypatch):
    monkeypatch.setenv("PMM_REFLECTION_COMMIT_DUE_HOURS", "0")
    db = tmp_path / "due2.db"
    log = EventLog(str(db))
    # Emit reflection to trigger commitment_open with due=now
    emit_reflection(log, "I will track evidence.")
    loop = AutonomyLoop(eventlog=log, cooldown=ReflectionCooldown())
    loop.tick()  # should create commitment_reminder once when due is passed

    evs = log.read_all()
    remind = [e for e in evs if e["kind"] == "commitment_reminder"]
    assert len(remind) >= 1
    assert remind[-1]["meta"]["status"] == "overdue"

    # Idempotency: second tick should not duplicate reminder for the same open
    loop.tick()
    evs2 = log.read_all()
    remind2 = [e for e in evs2 if e["kind"] == "commitment_reminder"]
    assert len(remind2) == len(remind)
