from __future__ import annotations

from pmm.core.event_log import EventLog
from pmm.core.mirror import Mirror


def create_sample_events(log: EventLog) -> None:
    # Append sample events for testing
    log.append(kind="user_message", content="hello", meta={"role": "user"})
    log.append(
        kind="assistant_message", content="COMMIT:task1", meta={"role": "assistant"}
    )
    log.append(
        kind="commitment_open", content="COMMIT:task1", meta={"source": "assistant"}
    )
    log.append(kind="reflection", content="reflected", meta={"source": "user"})
    for i in range(21):  # To trigger stale after 20 events
        log.append(kind="user_message", content=f"msg{i}", meta={"role": "user"})
    log.append(
        kind="commitment_close", content="CLOSE:task1", meta={"source": "assistant"}
    )


def test_rebuild_equals_incremental():
    log = EventLog(":memory:")
    create_sample_events(log)

    # Rebuild
    mirror_rebuild = Mirror(log)
    mirror_rebuild.rebuild()

    # Incremental
    mirror_inc = Mirror(log)
    events = log.read_all()
    for event in events:
        mirror_inc.sync(event)

    # Compare states
    assert mirror_rebuild.open_commitments == mirror_inc.open_commitments
    assert mirror_rebuild.stale_flags == mirror_inc.stale_flags
    assert mirror_rebuild.reflection_counts == mirror_inc.reflection_counts
    assert mirror_rebuild.last_event_id == mirror_inc.last_event_id


def test_sync_idempotent():
    log = EventLog(":memory:")
    log.append(kind="commitment_open", content="COMMIT:test", meta={"source": "user"})

    mirror = Mirror(log)
    event = log.read_all()[-1]

    # Sync multiple times
    mirror.sync(event)
    state1 = mirror.open_commitments.copy()
    mirror.sync(event)
    state2 = mirror.open_commitments.copy()

    assert state1 == state2


def test_stale_flag_triggers_after_21_events():
    log = EventLog(":memory:")
    log.append(kind="commitment_open", content="COMMIT:test", meta={"source": "user"})
    mirror = Mirror(log)

    # Add 20 more events
    for i in range(20):
        log.append(kind="user_message", content=f"msg{i}", meta={"role": "user"})
        mirror.sync(log.read_all()[-1])

    # Should not be stale yet (21st event makes it stale? Wait, threshold 20, so after 20 more, event_id diff =20, not >20?
    # STALE_THRESHOLD = 20, if current_id - event_id > 20
    # Initially event_id=1, after 20 events, current_id=21, 21-1=20, not >20, so not stale.
    # After 21st, 22-1=21 >20, stale.

    assert not mirror.stale_flags.get("test", False)

    log.append(kind="user_message", content="msg21", meta={"role": "user"})
    mirror.sync(log.read_all()[-1])

    assert mirror.stale_flags["test"]


def test_close_removes_from_open_and_stale():
    log = EventLog(":memory:")
    log.append(kind="commitment_open", content="COMMIT:test", meta={"source": "user"})
    mirror = Mirror(log)

    # Make it stale
    for i in range(21):
        log.append(kind="user_message", content=f"msg{i}", meta={"role": "user"})
        mirror.sync(log.read_all()[-1])

    assert mirror.stale_flags["test"]

    # Close
    log.append(kind="commitment_close", content="CLOSE:test", meta={"source": "user"})
    mirror.sync(log.read_all()[-1])

    assert "test" not in mirror.open_commitments
    assert "test" not in mirror.stale_flags
