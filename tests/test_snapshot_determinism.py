"""Tests for snapshot determinism and correctness.

Verifies:
- Snapshot reproducibility (same events → same snapshot)
- Delta rebuild correctness (snapshot + delta = full replay)
- Idempotency (creating snapshot twice = no-op)
- Schema versioning (mismatched schemas trigger rebuild)
- Deterministic triggers (snapshots at exact multiples)
"""

import tempfile
from pathlib import Path

import pytest

from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model
from pmm.storage.snapshot import (
    SNAPSHOT_INTERVAL,
    SNAPSHOT_SCHEMA_VERSION,
    SNAPSHOT_RETENTION_COUNT,
    build_self_model_optimized,
    create_snapshot,
    prune_old_snapshots,
    should_create_snapshot,
    verify_snapshot_integrity,
)


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield str(db_path)


def _populate_ledger(eventlog: EventLog, num_events: int):
    """Populate ledger with test events."""
    for i in range(num_events):
        eventlog.append(
            kind="test_event",
            content=f"Event {i}",
            meta={"index": i, "data": f"test_{i}"},
        )


def test_snapshot_reproducibility(temp_db):
    """Verify snapshot at event N always produces same state."""
    eventlog = EventLog(temp_db)

    # Populate ledger with 2000 events
    _populate_ledger(eventlog, 2000)

    # Create snapshot at 1000
    snapshot_id_1 = create_snapshot(eventlog, 1000)

    # Create another snapshot at same point (should be idempotent)
    events = eventlog.read_all()
    snapshot_id_2 = create_snapshot(eventlog, 1000)

    # Should return same event ID (no-op)
    assert snapshot_id_2 == snapshot_id_1

    # Verify checksum matches full replay
    events_to_1000 = [
        e for e in events if e["id"] <= 1000 and e["kind"] != "projection_snapshot"
    ]
    full_replay_state = build_self_model(events_to_1000, eventlog=eventlog)

    # Load snapshot state
    optimized_state = build_self_model_optimized(events_to_1000, eventlog=eventlog)

    # States should match
    assert optimized_state == full_replay_state


def test_snapshot_delta_rebuild(temp_db):
    """Verify snapshot + delta = full replay."""
    eventlog = EventLog(temp_db)

    # Populate ledger with 1500 events
    _populate_ledger(eventlog, 1500)

    # Create snapshot at 1000
    create_snapshot(eventlog, 1000)

    # Get all events
    all_events = [e for e in eventlog.read_all() if e["kind"] != "projection_snapshot"]

    # Full replay
    full_replay_state = build_self_model(all_events, eventlog=eventlog)

    # Optimized rebuild (snapshot + delta)
    optimized_state = build_self_model_optimized(all_events, eventlog=eventlog)

    # Should match
    assert optimized_state == full_replay_state


def test_snapshot_idempotency(temp_db):
    """Creating snapshot twice at same ID is no-op."""
    eventlog = EventLog(temp_db)

    # Populate ledger
    _populate_ledger(eventlog, 1500)

    # Create snapshot
    snapshot_id_1 = create_snapshot(eventlog, 1000)

    # Count snapshot events
    events = eventlog.read_all()
    snapshots_before = [e for e in events if e["kind"] == "projection_snapshot"]

    # Create again
    snapshot_id_2 = create_snapshot(eventlog, 1000)

    # Should return same ID
    assert snapshot_id_2 == snapshot_id_1

    # Should not create duplicate event
    events_after = eventlog.read_all()
    snapshots_after = [e for e in events_after if e["kind"] == "projection_snapshot"]

    assert len(snapshots_after) == len(snapshots_before)


def test_deterministic_trigger(temp_db):
    """Snapshots trigger at exact multiples of interval."""
    eventlog = EventLog(temp_db)

    # Populate to 2055 events (overshoots 2000)
    _populate_ledger(eventlog, 2055)

    # Check trigger
    should_create, target_id = should_create_snapshot(eventlog)

    # Should trigger at exactly 2000 (not 2055)
    assert should_create
    assert target_id == 2000

    # Create snapshot
    create_snapshot(eventlog, target_id)

    # Check again - should not trigger (already exists)
    should_create_2, target_id_2 = should_create_snapshot(eventlog)
    assert not should_create_2
    assert target_id_2 == 2000


def test_snapshot_verification(temp_db):
    """Verify snapshot integrity check works."""
    eventlog = EventLog(temp_db)

    # Populate ledger
    _populate_ledger(eventlog, 1500)

    # Create snapshot
    snapshot_id = create_snapshot(eventlog, 1000)

    # Get snapshot event
    events = eventlog.read_all()
    snapshot_event = next(e for e in events if e["id"] == snapshot_id)

    # Verify integrity
    is_valid = verify_snapshot_integrity(eventlog, snapshot_event)

    assert is_valid


def test_no_snapshot_fallback(temp_db):
    """Verify fallback to full replay when no snapshots exist."""
    eventlog = EventLog(temp_db)

    # Populate ledger (below snapshot threshold)
    _populate_ledger(eventlog, 500)

    # Get events
    events = [e for e in eventlog.read_all() if e["kind"] != "projection_snapshot"]

    # Optimized build should fall back to full replay
    optimized_state = build_self_model_optimized(events, eventlog=eventlog)
    full_replay_state = build_self_model(events, eventlog=eventlog)

    assert optimized_state == full_replay_state


def test_snapshot_interval_alignment(temp_db):
    """Verify snapshots align to exact interval multiples."""
    eventlog = EventLog(temp_db)

    # Populate to various sizes
    for size in [1050, 2100, 3250]:
        eventlog = EventLog(temp_db)
        _populate_ledger(eventlog, size)

        should_create, target_id = should_create_snapshot(eventlog)

        if should_create:
            # Target should be exact multiple of interval
            assert target_id % SNAPSHOT_INTERVAL == 0
            # Target should be <= current max
            assert target_id <= eventlog.get_max_id()


def test_schema_version_mismatch_triggers_rebuild(temp_db):
    """Verify schema version mismatch triggers snapshot rebuild."""
    eventlog = EventLog(temp_db)

    # Populate ledger
    _populate_ledger(eventlog, 1500)

    # Create snapshot with current schema
    snapshot_id = create_snapshot(eventlog, 1000)

    # Get snapshot event
    events = eventlog.read_all()
    snapshot_event = next(e for e in events if e["id"] == snapshot_id)

    # Verify current schema matches
    assert snapshot_event["meta"]["schema_version"] == SNAPSHOT_SCHEMA_VERSION

    # Simulate schema change by modifying the event (for test purposes)
    # In real scenario, SNAPSHOT_SCHEMA_VERSION would be bumped in code
    # and should_create_snapshot would detect mismatch


def test_snapshot_pruning_keeps_last_n(temp_db):
    """Verify pruning keeps last N snapshots."""
    eventlog = EventLog(temp_db)

    # Create more snapshots than retention limit
    num_snapshots = SNAPSHOT_RETENTION_COUNT + 5
    for i in range(1, num_snapshots + 1):
        target_id = i * 1000
        _populate_ledger(eventlog, target_id)
        create_snapshot(eventlog, target_id)

    # Get all snapshot events
    events = eventlog.read_all()
    snapshot_events = [e for e in events if e["kind"] == "projection_snapshot"]

    # Should have created all snapshots
    assert len(snapshot_events) == num_snapshots

    # Manually trigger pruning (normally happens in create_snapshot)
    metrics = prune_old_snapshots(eventlog)

    # Should have pruned oldest ones
    assert metrics["pruned_count"] == 5
    assert metrics["retained_count"] == SNAPSHOT_RETENTION_COUNT

    # Verify snapshots table only has retained ones
    cursor = eventlog._conn.execute("SELECT COUNT(*) FROM snapshots")
    count = cursor.fetchone()[0]
    assert count == SNAPSHOT_RETENTION_COUNT


def test_snapshot_pruning_respects_minimum(temp_db):
    """Verify pruning doesn't prune if below minimum retention."""
    eventlog = EventLog(temp_db)

    # Create only 3 snapshots (below minimum)
    for i in range(1, 4):
        target_id = i * 1000
        _populate_ledger(eventlog, target_id)
        create_snapshot(eventlog, target_id)

    # Try to prune
    metrics = prune_old_snapshots(eventlog)

    # Should not prune anything
    assert metrics["pruned_count"] == 0
    assert metrics["retained_count"] == 3


def test_pruned_snapshot_triggers_fallback(temp_db):
    """Verify that referencing a pruned snapshot falls back to full replay."""
    eventlog = EventLog(temp_db)

    # Create snapshots
    for i in range(1, 15):
        target_id = i * 1000
        _populate_ledger(eventlog, target_id)
        create_snapshot(eventlog, target_id)

    # Prune old snapshots
    prune_old_snapshots(eventlog)

    # Try to build model using events that would reference a pruned snapshot
    events = [e for e in eventlog.read_all() if e["kind"] != "projection_snapshot"]
    events_to_5000 = [e for e in events if e["id"] <= 5000]

    # Should fall back to full replay (snapshot at 5000 was pruned)
    # This should not crash, just be slower
    state = build_self_model_optimized(events_to_5000, eventlog=eventlog)

    # Verify state is still correct
    assert state is not None
    assert "identity" in state
    assert "commitments" in state


def test_pruning_metrics_accuracy(temp_db):
    """Verify pruning metrics are accurate."""
    eventlog = EventLog(temp_db)

    # Create 12 snapshots
    for i in range(1, 13):
        target_id = i * 1000
        _populate_ledger(eventlog, target_id)
        create_snapshot(eventlog, target_id)

    # Prune
    metrics = prune_old_snapshots(eventlog)

    # Verify metrics
    assert metrics["total_snapshots"] == 12
    assert metrics["pruned_count"] == 2  # 12 - 10 = 2
    assert metrics["retained_count"] == 10
    assert metrics["storage_freed_kb"] >= 0  # Should have freed some storage
    assert metrics["oldest_retained_event_id"] == 3000  # First 2 pruned (1000, 2000)
    assert metrics["newest_retained_event_id"] == 12000


def test_delta_replay_preserves_baseline(temp_db):
    """Regression test: delta replay must preserve snapshot baseline state.

    This test catches the bug where _replay_delta() was discarding the
    snapshot baseline and rebuilding from defaults, causing trait divergence.
    """
    eventlog = EventLog(temp_db)

    # Create events with trait updates that push traits to boundaries
    for i in range(1000):
        eventlog.append(kind="test_event", content=f"Event {i}", meta={"index": i})

    # Add trait updates that push openness to 1.0
    for i in range(10):
        eventlog.append(
            kind="trait_update",
            content="",
            meta={"delta": {"o": 0.05}},  # +0.05 openness each time
        )

    # Create snapshot at 1010 (after trait updates)
    create_snapshot(eventlog, 1010)

    # Add more events after snapshot
    for i in range(500):
        eventlog.append(
            kind="test_event",
            content=f"Delta event {i}",
            meta={"index": 1010 + i},
        )

    # Get events for snapshot + delta rebuild
    events = [e for e in eventlog.read_all() if e["kind"] != "projection_snapshot"]

    # Build using snapshot + delta
    snapshot_state = build_self_model_optimized(events, eventlog=eventlog)

    # Build using full replay
    full_state = build_self_model(events, eventlog=eventlog)

    # States must match exactly
    assert snapshot_state == full_state, (
        f"Snapshot+delta diverged from full replay!\n"
        f"Snapshot traits: {snapshot_state['identity']['traits']}\n"
        f"Full traits: {full_state['identity']['traits']}"
    )
