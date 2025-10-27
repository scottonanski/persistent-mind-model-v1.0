"""Tests for EventIndex pointer index functionality."""

import tempfile
from pathlib import Path

from pmm.storage.event_index import EventIndex
from pmm.storage.eventlog import EventLog


class TestEventIndex:
    """Test suite for EventIndex functionality."""

    def test_empty_index(self):
        """Test index behavior with empty eventlog."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))
            index = EventIndex(eventlog)

            # Empty index should have no events
            assert index.get_stats()["indexed_events"] == 0
            assert index.get_stats()["max_indexed_id"] == 0

            # Reading by IDs should return empty list
            assert index.read_by_ids([1, 2, 3]) == []

            # Index scan should be empty
            assert list(index.index_scan()) == []

    def test_basic_indexing(self):
        """Test basic event indexing and retrieval."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))

            # Add some test events
            eid1 = eventlog.append(
                kind="test_event", content="First event", meta={"test": True}
            )
            eventlog.append(
                kind="reflection", content="Test reflection", meta={"novelty": 0.8}
            )
            eid3 = eventlog.append(
                kind="commitment_open",
                content="Test commitment",
                meta={"cid": "test123"},
            )

            # Create index after events exist
            index = EventIndex(eventlog)

            # Verify index stats
            stats = index.get_stats()
            assert stats["indexed_events"] == 3
            assert stats["max_indexed_id"] == eid3

            # Test metadata retrieval
            meta1 = index.get_event_meta(eid1)
            assert meta1 is not None
            assert meta1.event_id == eid1
            assert meta1.kind == "test_event"
            assert len(meta1.content_hash) == 64  # SHA256 hex length

            # Test reading by IDs
            events = index.read_by_ids([eid1, eid3])
            assert len(events) == 2
            assert events[0]["id"] == eid1
            assert events[0]["content"] == "First event"
            assert events[1]["id"] == eid3
            assert events[1]["content"] == "Test commitment"

    def test_incremental_indexing(self):
        """Test that index updates when new events are added."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))

            # Create index with empty eventlog
            index = EventIndex(eventlog)
            assert index.get_stats()["indexed_events"] == 0

            # Add event after index creation
            eid1 = eventlog.append(
                kind="test_event", content="Added after index", meta={}
            )

            # Index should automatically update
            stats = index.get_stats()
            assert stats["indexed_events"] == 1
            assert stats["max_indexed_id"] == eid1

            # Should be able to retrieve the new event
            meta = index.get_event_meta(eid1)
            assert meta is not None
            assert meta.event_id == eid1
            assert meta.kind == "test_event"

    def test_hash_verification(self):
        """Test hash verification functionality."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))

            # Add test event
            eid = eventlog.append(
                kind="test_event", content="Hash test", meta={"verify": True}
            )

            index = EventIndex(eventlog)

            # Read without hash verification (should work)
            events_no_verify = index.read_by_ids([eid], verify_hash=False)
            assert len(events_no_verify) == 1

            # Read with hash verification (should also work with valid hashes)
            events_verify = index.read_by_ids([eid], verify_hash=True)
            assert len(events_verify) == 1
            assert events_verify[0]["content"] == "Hash test"

    def test_missing_events(self):
        """Test behavior with missing event IDs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))

            # Add one event
            eid = eventlog.append(kind="test_event", content="Only event", meta={})

            index = EventIndex(eventlog)

            # Request mix of existing and non-existing IDs
            events = index.read_by_ids([999, eid, 1000])

            # Should only return the existing event
            assert len(events) == 1
            assert events[0]["id"] == eid

            # Non-existing event should return None for metadata
            assert index.get_event_meta(999) is None

    def test_index_scan_ordering(self):
        """Test that index_scan returns events in deterministic order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))

            # Add events in order
            eids = []
            for i in range(5):
                eid = eventlog.append(
                    kind=f"event_{i}", content=f"Event {i}", meta={"index": i}
                )
                eids.append(eid)

            index = EventIndex(eventlog)

            # Scan should return events in ID order
            scanned = list(index.index_scan())
            assert len(scanned) == 5

            for i, meta in enumerate(scanned):
                assert meta.event_id == eids[i]
                assert meta.kind == f"event_{i}"

    def test_event_kinds_preserved(self):
        """Test that different event kinds are properly indexed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))

            # Add events of different kinds
            kinds = [
                "identity_adopt",
                "reflection",
                "commitment_open",
                "policy_update",
                "autonomy_tick",
            ]

            eids = []
            for kind in kinds:
                eid = eventlog.append(kind=kind, content=f"Test {kind}", meta={})
                eids.append(eid)

            index = EventIndex(eventlog)

            # Verify all kinds are preserved
            for i, kind in enumerate(kinds):
                meta = index.get_event_meta(eids[i])
                assert meta is not None
                assert meta.kind == kind

    def test_large_batch_read(self):
        """Test reading many events at once."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))

            # Add 100 events
            eids = []
            for i in range(100):
                eid = eventlog.append(
                    kind="batch_test", content=f"Batch event {i}", meta={"batch_id": i}
                )
                eids.append(eid)

            index = EventIndex(eventlog)

            # Read all events at once
            events = index.read_by_ids(eids)
            assert len(events) == 100

            # Verify order and content
            for i, event in enumerate(events):
                assert event["id"] == eids[i]
                assert event["content"] == f"Batch event {i}"
                assert event["meta"]["batch_id"] == i

    def test_deterministic_hashing(self):
        """Test that event hashing is deterministic."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))

            # Add identical events
            eid1 = eventlog.append(
                kind="hash_test",
                content="Identical content",
                meta={"key": "value", "number": 42},
            )
            eid2 = eventlog.append(
                kind="hash_test",
                content="Identical content",
                meta={"key": "value", "number": 42},
            )

            index = EventIndex(eventlog)

            # Events should have different IDs but same content structure
            meta1 = index.get_event_meta(eid1)
            meta2 = index.get_event_meta(eid2)

            assert meta1 is not None
            assert meta2 is not None
            assert meta1.event_id != meta2.event_id  # Different IDs
            # Hashes will be different because IDs are included in hash calculation
            assert meta1.content_hash != meta2.content_hash
