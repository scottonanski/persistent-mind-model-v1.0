import time
import datetime as dt

from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import AutonomyLoop
from pmm.runtime.cooldown import ReflectionCooldown


def _make_loop(log: EventLog) -> AutonomyLoop:
    cd = ReflectionCooldown()
    return AutonomyLoop(eventlog=log, cooldown=cd, interval_seconds=0.1)


def test_future_due_no_reminder(tmp_path):
    db = tmp_path / "reminders1.db"
    log = EventLog(str(db))
    # Open a commitment with due 1 hour in the future
    cid = "c1"
    future_ts = int(time.time()) + 3600
    log.append(
        kind="commitment_open",
        content="Commitment opened: demo",
        meta={"cid": cid, "text": "demo", "due": future_ts},
    )
    loop = _make_loop(log)
    loop.tick()
    evs = log.read_all()
    assert not any(e.get("kind") == "commitment_reminder" for e in evs)


def test_past_due_single_reminder(tmp_path):
    db = tmp_path / "reminders2.db"
    log = EventLog(str(db))
    # Open a commitment with due 1 hour in the past
    cid = "c2"
    past_ts = int(time.time()) - 3600
    log.append(
        kind="commitment_open",
        content="Commitment opened: demo2",
        meta={"cid": cid, "text": "demo2", "due": past_ts},
    )
    loop = _make_loop(log)
    loop.tick()
    evs = log.read_all()
    reminders = [e for e in evs if e.get("kind") == "commitment_reminder"]
    assert len(reminders) == 1
    m = reminders[0].get("meta") or {}
    assert m.get("cid") == cid
    assert m.get("status") == "overdue"


def test_no_duplicate_reminders_across_ticks(tmp_path):
    db = tmp_path / "reminders3.db"
    log = EventLog(str(db))
    cid = "c3"
    # Use ISO timestamp in the past to validate parsing path
    past_iso = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).isoformat()
    log.append(
        kind="commitment_open",
        content="Commitment opened: demo3",
        meta={"cid": cid, "text": "demo3", "due": past_iso},
    )
    loop = _make_loop(log)
    loop.tick()
    loop.tick()
    evs = log.read_all()
    reminders = [
        e
        for e in evs
        if e.get("kind") == "commitment_reminder"
        and (e.get("meta") or {}).get("cid") == cid
    ]
    assert len(reminders) == 1
