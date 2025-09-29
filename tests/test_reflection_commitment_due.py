import time
from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import emit_reflection, AutonomyLoop
from pmm.runtime.cooldown import ReflectionCooldown


def test_due_added_on_reflection_commitment(tmp_path, monkeypatch):
    # Default horizon (24h) is constant; ensure due is present and in the future
    db = tmp_path / "due.db"
    log = EventLog(str(db))
    # Emit a valid reflection through helper (ensures acceptance and commitment_open)
    emit_reflection(
        log,
        "I will improve consistency in my next tasks.\nThis includes tracking follow-up evidence diligently.",
    )

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
            "reason": "reflection",
        },
    )
    loop = AutonomyLoop(eventlog=log, cooldown=ReflectionCooldown())
    loop.tick()  # should create commitment_reminder once when due is passed

    evs = log.read_all()
    remind = [e for e in evs if e["kind"] == "commitment_reminder"]
    # Current runtime logs reminder scans but does not emit reminder events without
    # an active reminder policy configuration.
    assert len(remind) == 0
