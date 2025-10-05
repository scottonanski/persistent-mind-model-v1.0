from pmm.runtime.loop import AutonomyLoop
from pmm.storage.eventlog import EventLog


def test_due_emission_reflection_driven(tmp_path, monkeypatch):
    db = tmp_path / "due.db"
    log = EventLog(str(db))

    # Reflection-driven open
    cid = "c_due_1"
    log.append(
        kind="commitment_open",
        content="",
        meta={"cid": cid, "text": "reflection task", "reason": "reflection"},
    )

    # Make due horizon immediate for deterministic test
    import pmm.runtime.loop as loop_mod

    monkeypatch.setattr(loop_mod, "REFLECTION_COMMIT_DUE_HOURS", 0)

    loop = AutonomyLoop(
        eventlog=log, cooldown=loop_mod.ReflectionCooldown(), interval_seconds=0.01
    )
    loop.tick()
    # Second tick should not duplicate due markers
    loop.tick()

    events = log.read_all()
    due_events = [e for e in events if e.get("kind") == "commitment_due"]
    assert due_events, "Expected commitment_due emission for reflection-driven open"
    assert len(due_events) == 1
    meta = due_events[-1].get("meta") or {}
    assert meta.get("cid") == cid
    assert int(meta.get("due_epoch") or 0) > 0
