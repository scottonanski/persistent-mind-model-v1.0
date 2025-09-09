import datetime as dt

from pmm.runtime.prioritizer import rank_commitments
from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import AutonomyLoop
from pmm.runtime.cooldown import ReflectionCooldown


def _append_open(log: EventLog, cid: str, text: str, ts: str | None = None):
    if ts:
        # EventLog doesn't allow custom ts on append; emulate by direct sqlite write is out of scope.
        # Instead, we'll manipulate age by appending earlier and waiting, but that's brittle.
        # So we craft events manually and use rank_commitments on in-memory events for determinism.
        pass


def _mk_events_for_urgency():
    now = dt.datetime.now(dt.UTC)

    def iso(t):
        return t.isoformat()

    # Create synthetic events list with custom timestamps to control ages
    events = []
    # Open three commitments at different times
    events.append(
        {
            "id": 1,
            "ts": iso(now - dt.timedelta(hours=20)),
            "kind": "commitment_open",
            "content": "",
            "meta": {"cid": "a", "text": "task a"},
        }
    )
    events.append(
        {
            "id": 2,
            "ts": iso(now - dt.timedelta(hours=10)),
            "kind": "commitment_open",
            "content": "",
            "meta": {"cid": "b", "text": "task b"},
        }
    )
    events.append(
        {
            "id": 3,
            "ts": iso(now - dt.timedelta(hours=2)),
            "kind": "commitment_open",
            "content": "",
            "meta": {"cid": "c", "text": "task c"},
        }
    )
    return events


def _mk_events_for_novelty():
    now = dt.datetime.now(dt.UTC)

    def iso(t):
        return t.isoformat()

    events = []
    # Recent assistant replies similar to commitment x, dissimilar to y
    events.append(
        {
            "id": 1,
            "ts": iso(now - dt.timedelta(minutes=5)),
            "kind": "response",
            "content": "write docs quickly",
            "meta": {},
        }
    )
    events.append(
        {
            "id": 2,
            "ts": iso(now - dt.timedelta(minutes=4)),
            "kind": "response",
            "content": "finish docs now",
            "meta": {},
        }
    )
    # Two commitments
    events.append(
        {
            "id": 3,
            "ts": iso(now - dt.timedelta(minutes=3)),
            "kind": "commitment_open",
            "content": "",
            "meta": {"cid": "x", "text": "write the docs"},
        }
    )
    events.append(
        {
            "id": 4,
            "ts": iso(now - dt.timedelta(minutes=2)),
            "kind": "commitment_open",
            "content": "",
            "meta": {"cid": "y", "text": "explore new algorithm"},
        }
    )
    return events


def _mk_events_for_priority_update_event():
    now = dt.datetime.now(dt.UTC)

    def iso(t):
        return t.isoformat()

    events = []
    # A few opens and a reply
    events.append(
        {
            "id": 1,
            "ts": iso(now - dt.timedelta(hours=5)),
            "kind": "commitment_open",
            "content": "",
            "meta": {"cid": "a", "text": "alpha"},
        }
    )
    events.append(
        {
            "id": 2,
            "ts": iso(now - dt.timedelta(hours=4)),
            "kind": "commitment_open",
            "content": "",
            "meta": {"cid": "b", "text": "bravo"},
        }
    )
    events.append(
        {
            "id": 3,
            "ts": iso(now - dt.timedelta(minutes=10)),
            "kind": "response",
            "content": "misc reply",
            "meta": {},
        }
    )
    return events


def test_urgency_ranks_older_higher():
    events = _mk_events_for_urgency()
    ranking = rank_commitments(events)
    # 'a' is oldest -> highest urgency, then 'b', then 'c'
    assert [cid for cid, _ in ranking] == ["a", "b", "c"]


def test_novelty_boosts_dissimilar_commitment():
    events = _mk_events_for_novelty()
    ranking = rank_commitments(events)
    # 'y' (explore new algorithm) is more novel than 'x' (write docs)
    assert ranking[0][0] == "y"


def test_priority_update_event_emitted(tmp_path):
    log = EventLog(str(tmp_path / "prio.db"))
    # Seed some events
    for ev in _mk_events_for_priority_update_event():
        log.append(kind=ev["kind"], content=ev["content"], meta=ev.get("meta"))
    loop = AutonomyLoop(
        eventlog=log, cooldown=ReflectionCooldown(), interval_seconds=0.01
    )
    loop.tick()
    events = log.read_all()
    pr = [e for e in events if e.get("kind") == "priority_update"]
    assert pr, "priority_update event should be appended"
    # ranking should include entries
    ranking = (pr[-1].get("meta") or {}).get("ranking")
    assert ranking and isinstance(ranking, list)
