from pmm.runtime.loop import AutonomyLoop
from pmm.storage.eventlog import EventLog


def test_due_suppressed_after_close(tmp_path, monkeypatch):
    db = tmp_path / "due_close.db"
    log = EventLog(str(db))

    cid = "c_due_close"
    log.append(
        kind="commitment_open",
        content="",
        meta={"cid": cid, "text": "reflection task", "reason": "reflection"},
    )
    # Close before due should emit
    log.append(
        kind="commitment_close",
        content="",
        meta={"cid": cid, "evidence_type": "done", "source": "test"},
    )

    # Make due horizon immediate for deterministic test
    import pmm.runtime.loop as loop_mod

    monkeypatch.setattr(loop_mod, "REFLECTION_COMMIT_DUE_HOURS", 0)

    loop = AutonomyLoop(
        eventlog=log, cooldown=loop_mod.ReflectionCooldown(), interval_seconds=0.01
    )
    loop.tick()

    due_events = [e for e in log.read_all() if e.get("kind") == "commitment_due"]
    assert not due_events, "No commitment_due after close/expire"


def test_due_respects_snooze_until_tick(tmp_path, monkeypatch):
    db = tmp_path / "due_snooze.db"
    log = EventLog(str(db))

    cid = "c_due_snooze"
    log.append(
        kind="commitment_open",
        content="",
        meta={"cid": cid, "text": "reflection task", "reason": "reflection"},
    )

    # Snooze until tick 3
    log.append(
        kind="commitment_snooze",
        content="",
        meta={"cid": cid, "until_tick": 3},
    )

    # Immediate horizon
    import pmm.runtime.loop as loop_mod

    monkeypatch.setattr(loop_mod, "REFLECTION_COMMIT_DUE_HOURS", 0)

    loop = AutonomyLoop(
        eventlog=log, cooldown=loop_mod.ReflectionCooldown(), interval_seconds=0.01
    )
    # Run 2 ticks (current_tick before emission: 0 then 1) — snooze should suppress
    loop.tick()
    loop.tick()
    due_events_pre = [e for e in log.read_all() if e.get("kind") == "commitment_due"]
    assert not due_events_pre, "Snooze should suppress early due"

    # Advance more ticks so current_tick > until_tick (need >3, compute occurs before appending)
    loop.tick()
    loop.tick()
    loop.tick()
    due_events = [e for e in log.read_all() if e.get("kind") == "commitment_due"]
    assert (
        due_events and len(due_events) == 1
    ), "Due should emit once after snooze window"


def test_due_not_for_non_reflection(tmp_path, monkeypatch):
    db = tmp_path / "due_non_reflection.db"
    log = EventLog(str(db))

    cid = "c_due_nonrefl"
    log.append(
        kind="commitment_open",
        content="",
        meta={"cid": cid, "text": "task", "reason": "user"},
    )

    import pmm.runtime.loop as loop_mod

    monkeypatch.setattr(loop_mod, "REFLECTION_COMMIT_DUE_HOURS", 0)
    loop = AutonomyLoop(
        eventlog=log, cooldown=loop_mod.ReflectionCooldown(), interval_seconds=0.01
    )
    loop.tick()
    due_events = [e for e in log.read_all() if e.get("kind") == "commitment_due"]
    assert not due_events, "Non-reflection opens should not emit due"


def test_due_not_reemit_across_restart(tmp_path, monkeypatch):
    db = tmp_path / "due_restart.db"
    log = EventLog(str(db))

    cid = "c_due_restart"
    log.append(
        kind="commitment_open",
        content="",
        meta={"cid": cid, "text": "reflection task", "reason": "reflection"},
    )
    import pmm.runtime.loop as loop_mod

    monkeypatch.setattr(loop_mod, "REFLECTION_COMMIT_DUE_HOURS", 0)

    # First run emits due
    loop = AutonomyLoop(
        eventlog=log, cooldown=loop_mod.ReflectionCooldown(), interval_seconds=0.01
    )
    loop.tick()
    events1 = log.read_all()
    due_events1 = [e for e in events1 if e.get("kind") == "commitment_due"]
    assert due_events1 and len(due_events1) == 1

    # New loop instance (replay) should not emit duplicate due
    loop2 = AutonomyLoop(
        eventlog=log, cooldown=loop_mod.ReflectionCooldown(), interval_seconds=0.01
    )
    loop2.tick()
    events2 = log.read_all()
    due_events2 = [e for e in events2 if e.get("kind") == "commitment_due"]
    assert len(due_events2) == 1


def test_due_respects_latest_snooze(tmp_path, monkeypatch):
    db = tmp_path / "due_multi_snooze.db"
    log = EventLog(str(db))

    cid = "c_due_multi"
    log.append(
        kind="commitment_open",
        content="",
        meta={"cid": cid, "text": "reflection task", "reason": "reflection"},
    )

    # Two snoozes: until 2, then until 5; latest should win
    log.append(kind="commitment_snooze", content="", meta={"cid": cid, "until_tick": 2})
    log.append(kind="commitment_snooze", content="", meta={"cid": cid, "until_tick": 5})

    import pmm.runtime.loop as loop_mod

    monkeypatch.setattr(loop_mod, "REFLECTION_COMMIT_DUE_HOURS", 0)
    loop = AutonomyLoop(
        eventlog=log, cooldown=loop_mod.ReflectionCooldown(), interval_seconds=0.01
    )

    # Run 4 ticks: current_tick progresses 0,1,2,3 — still <= 5 => no due
    loop.tick()
    loop.tick()
    loop.tick()
    loop.tick()
    assert not [e for e in log.read_all() if e.get("kind") == "commitment_due"]

    # Advance beyond 5 to allow due emission (compute sees count before appending this tick)
    loop.tick()
    loop.tick()
    loop.tick()
    dues = [e for e in log.read_all() if e.get("kind") == "commitment_due"]
    assert dues and len(dues) == 1


def test_due_not_reemit_after_snooze_post_due(tmp_path, monkeypatch):
    db = tmp_path / "due_post_snooze.db"
    log = EventLog(str(db))

    cid = "c_due_post_snooze"
    log.append(
        kind="commitment_open",
        content="",
        meta={"cid": cid, "text": "reflection task", "reason": "reflection"},
    )
    import pmm.runtime.loop as loop_mod

    monkeypatch.setattr(loop_mod, "REFLECTION_COMMIT_DUE_HOURS", 0)
    loop = AutonomyLoop(
        eventlog=log, cooldown=loop_mod.ReflectionCooldown(), interval_seconds=0.01
    )
    # Emit initial due
    loop.tick()
    events1 = log.read_all()
    assert [e for e in events1 if e.get("kind") == "commitment_due"]

    # Snooze after due emission; policy does not re-emit additional due markers
    log.append(
        kind="commitment_snooze", content="", meta={"cid": cid, "until_tick": 10}
    )
    # Advance ticks — no duplicate due
    loop.tick()
    loop.tick()
    loop.tick()
    events2 = log.read_all()
    dues = [e for e in events2 if e.get("kind") == "commitment_due"]
    assert len(dues) == 1


def test_due_emits_after_horizon_decrease(tmp_path, monkeypatch):
    db = tmp_path / "due_horizon.db"
    log = EventLog(str(db))

    cid = "c_due_horizon"
    log.append(
        kind="commitment_open",
        content="",
        meta={"cid": cid, "text": "reflection task", "reason": "reflection"},
    )

    import pmm.runtime.loop as loop_mod

    # Start with large horizon to avoid due
    monkeypatch.setattr(loop_mod, "REFLECTION_COMMIT_DUE_HOURS", 100)
    loop = AutonomyLoop(
        eventlog=log, cooldown=loop_mod.ReflectionCooldown(), interval_seconds=0.01
    )
    loop.tick()
    assert not [e for e in log.read_all() if e.get("kind") == "commitment_due"]

    # Reduce horizon to 0 — due should emit on next tick
    monkeypatch.setattr(loop_mod, "REFLECTION_COMMIT_DUE_HOURS", 0)
    loop.tick()
    dues = [e for e in log.read_all() if e.get("kind") == "commitment_due"]
    assert dues and len(dues) == 1
