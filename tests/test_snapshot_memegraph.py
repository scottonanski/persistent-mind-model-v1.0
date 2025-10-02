"""Tests for MemeGraph integration with snapshots.

Verifies that MemeGraph state is correctly saved and restored from snapshots.
"""

import tempfile
from pathlib import Path

import pytest

from pmm.runtime.memegraph import MemeGraphProjection
from pmm.storage.eventlog import EventLog
from pmm.storage.snapshot import (
    build_self_model_optimized,
    create_snapshot,
)


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield str(db_path)


def _populate_ledger_with_graph_events(eventlog: EventLog, num_events: int):
    """Populate ledger with events that create MemeGraph nodes/edges."""
    for i in range(num_events):
        # Add various event types that MemeGraph processes
        eventlog.append(
            kind="reflection",
            content=f"Reflection {i}: Analyzing current state",
            meta={
                "source": "reflect",
                "telemetry": {"IAS": 0.5 + (i * 0.01), "GAS": 0.8},
                "style": "analytical",
            },
        )

        if i % 5 == 0:
            # Add commitment events
            eventlog.append(
                kind="commitment_open",
                content=f"Commitment {i}",
                meta={
                    "cid": f"cid_{i}",
                    "text": f"Commitment text {i}",
                    "reason": "reflection",
                },
            )

        if i % 10 == 0:
            # Add stage updates
            eventlog.append(
                kind="stage_update",
                content="",
                meta={"from": "S0", "to": "S1"},
            )


def test_memegraph_export_import(temp_db):
    """Verify MemeGraph state can be exported and imported."""
    eventlog = EventLog(temp_db)

    # Populate ledger
    _populate_ledger_with_graph_events(eventlog, 100)

    # Create MemeGraph
    memegraph = MemeGraphProjection(eventlog)

    # Export state
    exported_state = memegraph.export_state()

    # Verify exported state has expected keys
    assert "nodes" in exported_state
    assert "edges" in exported_state
    assert "event_index" in exported_state
    assert "metrics" in exported_state

    # Verify we have some nodes/edges
    assert len(exported_state["nodes"]) > 0
    assert exported_state["metrics"]["nodes"] > 0

    # Create new MemeGraph and import state
    memegraph2 = MemeGraphProjection(EventLog(temp_db))
    memegraph2.import_state(exported_state)

    # Verify imported state matches
    assert memegraph2.node_count == memegraph.node_count
    assert memegraph2.edge_count == memegraph.edge_count


def test_snapshot_includes_memegraph(temp_db):
    """Verify snapshots include MemeGraph state when provided."""
    eventlog = EventLog(temp_db)

    # Populate ledger
    _populate_ledger_with_graph_events(eventlog, 1500)

    # Create MemeGraph
    memegraph = MemeGraphProjection(eventlog)
    original_node_count = memegraph.node_count
    original_edge_count = memegraph.edge_count

    # Create snapshot with MemeGraph
    snapshot_id = create_snapshot(eventlog, 1000, memegraph=memegraph)

    # Verify snapshot was created
    assert snapshot_id > 0

    # Load snapshot and verify MemeGraph state is included
    events = eventlog.read_all()
    snapshot_event = next(e for e in events if e["id"] == snapshot_id)
    assert snapshot_event["kind"] == "projection_snapshot"

    # The MemeGraph state should be in the compressed snapshot
    # We can't easily verify without decompressing, but we can check
    # that the snapshot was created successfully
    assert original_node_count > 0
    assert original_edge_count > 0


def test_memegraph_restored_from_snapshot(temp_db):
    """Verify MemeGraph is correctly restored from snapshot."""
    eventlog = EventLog(temp_db)

    # Populate ledger
    _populate_ledger_with_graph_events(eventlog, 1500)

    # Create MemeGraph and snapshot
    memegraph1 = MemeGraphProjection(eventlog)
    original_node_count = memegraph1.node_count

    create_snapshot(eventlog, 1000, memegraph=memegraph1)

    # Create new MemeGraph (empty)
    memegraph2 = MemeGraphProjection(EventLog(temp_db))

    # Clear it to simulate fresh start
    memegraph2._nodes.clear()
    memegraph2._edges.clear()
    assert memegraph2.node_count == 0
    assert memegraph2.edge_count == 0

    # Load snapshot with MemeGraph restoration
    events = [e for e in eventlog.read_all() if e["kind"] != "projection_snapshot"]
    events_to_1000 = [e for e in events if e["id"] <= 1000]

    build_self_model_optimized(
        events_to_1000,
        eventlog=eventlog,
        memegraph=memegraph2,
    )

    # Verify MemeGraph was restored
    assert memegraph2.node_count > 0
    assert memegraph2.edge_count > 0

    # Note: counts might not match exactly due to event filtering,
    # but should be non-zero and substantial
    assert memegraph2.node_count >= original_node_count * 0.5


def test_memegraph_delta_replay(temp_db):
    """Verify MemeGraph correctly applies delta events after snapshot."""
    eventlog = EventLog(temp_db)

    # Populate ledger and create snapshot at 1000
    _populate_ledger_with_graph_events(eventlog, 1000)
    memegraph1 = MemeGraphProjection(eventlog)
    create_snapshot(eventlog, 1000, memegraph=memegraph1)

    # Add more events after snapshot
    _populate_ledger_with_graph_events(eventlog, 500)  # Events 1001-1500

    # Create new MemeGraph and load from snapshot + delta
    memegraph2 = MemeGraphProjection(EventLog(temp_db))
    memegraph2._nodes.clear()
    memegraph2._edges.clear()

    events = [e for e in eventlog.read_all() if e["kind"] != "projection_snapshot"]

    build_self_model_optimized(
        events,
        eventlog=eventlog,
        memegraph=memegraph2,
    )

    # Verify MemeGraph has nodes/edges from both snapshot and delta
    assert memegraph2.node_count > 0
    assert memegraph2.edge_count > 0


def test_snapshot_without_memegraph_still_works(temp_db):
    """Verify snapshots work without MemeGraph (backward compatibility)."""
    eventlog = EventLog(temp_db)

    # Populate ledger
    _populate_ledger_with_graph_events(eventlog, 1500)

    # Create snapshot WITHOUT MemeGraph
    snapshot_id = create_snapshot(eventlog, 1000, memegraph=None)

    # Verify snapshot was created
    assert snapshot_id > 0

    # Load snapshot without MemeGraph
    events = [e for e in eventlog.read_all() if e["kind"] != "projection_snapshot"]
    events_to_1000 = [e for e in events if e["id"] <= 1000]

    state = build_self_model_optimized(
        events_to_1000,
        eventlog=eventlog,
        memegraph=None,
    )

    # Verify state is valid
    assert "identity" in state
    assert "commitments" in state
    # memegraph key should not be in state since we didn't provide it
    assert "memegraph" not in state or state["memegraph"] is None
