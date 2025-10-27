"""Tests for EventRouter semantic routing functionality."""

import tempfile
from pathlib import Path

from pmm.runtime.event_router import ContextQuery, EventRouter
from pmm.storage.event_index import EventIndex
from pmm.storage.eventlog import EventLog


class TestEventRouter:
    """Test suite for EventRouter functionality."""

    def test_empty_router(self):
        """Test router behavior with empty eventlog."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))
            event_index = EventIndex(eventlog)
            router = EventRouter(eventlog, event_index)

            # Empty router should have no events
            stats = router.get_stats()
            assert stats["indexed_events"] == 0
            assert stats["kinds_indexed"] == 0

            # Routing should return empty list
            query = ContextQuery(required_kinds=["reflection"], semantic_terms=["test"])
            results = router.route(query)
            assert results == []

    def test_basic_routing(self):
        """Test basic event routing by kind."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))

            # Add test events
            eid1 = eventlog.append(
                kind="identity_adopt", content="Echo", meta={"source": "user"}
            )
            eid2 = eventlog.append(
                kind="reflection",
                content="Test reflection about growth",
                meta={"novelty": 0.8},
            )
            eid3 = eventlog.append(
                kind="commitment_open",
                content="I will improve my responses",
                meta={"cid": "test123"},
            )

            # Create router
            event_index = EventIndex(eventlog)
            router = EventRouter(eventlog, event_index)

            # Test routing by required kinds
            query = ContextQuery(
                required_kinds=["reflection", "commitment_open"],
                semantic_terms=[],
                limit=10,
            )
            results = router.route(query)

            # Should return reflection and commitment events
            assert len(results) == 2
            assert eid2 in results
            assert eid3 in results
            assert eid1 not in results  # identity_adopt not requested

    def test_semantic_routing(self):
        """Test semantic content matching."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))

            # Add events with different content
            eid1 = eventlog.append(
                kind="reflection",
                content="Thinking about growth and improvement",
                meta={},
            )
            eventlog.append(
                kind="reflection", content="Analysis of commitment patterns", meta={}
            )
            eventlog.append(
                kind="reflection", content="Random thoughts about weather", meta={}
            )

            event_index = EventIndex(eventlog)
            router = EventRouter(eventlog, event_index)

            # Query for growth-related content
            query = ContextQuery(
                required_kinds=[], semantic_terms=["growth", "improvement"], limit=10
            )
            results = router.route(query)

            # Should prioritize content with matching terms
            assert len(results) >= 1
            assert eid1 in results  # Contains "growth" and "improvement"

    def test_recency_bias(self):
        """Test that recent events are weighted higher."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))

            # Add events in sequence
            eid1 = eventlog.append(
                kind="reflection", content="Early reflection", meta={}
            )
            eventlog.append(kind="reflection", content="Middle reflection", meta={})
            eid3 = eventlog.append(
                kind="reflection", content="Recent reflection", meta={}
            )

            event_index = EventIndex(eventlog)
            router = EventRouter(eventlog, event_index)

            # Query with high recency bias
            query = ContextQuery(
                required_kinds=["reflection"],
                semantic_terms=[],
                recency_boost=0.9,  # Strong recency bias
                limit=10,
            )
            results = router.route(query)

            # More recent events should come first
            assert len(results) == 3
            assert results[0] == eid3  # Most recent first
            assert results[-1] == eid1  # Oldest last

    def test_structural_indices(self):
        """Test structural relationship tracking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))

            # Add identity events
            eid1 = eventlog.append(
                kind="identity_adopt", content="Echo", meta={"source": "user"}
            )
            eid2 = eventlog.append(
                kind="identity_adopt", content="Assistant", meta={"source": "user"}
            )

            # Add commitment chain
            eid3 = eventlog.append(
                kind="commitment_open",
                content="Test commitment",
                meta={"cid": "test123"},
            )
            eid4 = eventlog.append(
                kind="commitment_close",
                content="Commitment completed",
                meta={"cid": "test123"},
            )

            event_index = EventIndex(eventlog)
            router = EventRouter(eventlog, event_index)

            # Test identity timeline
            identity_timeline = router.get_identity_timeline()
            assert identity_timeline == [eid1, eid2]

            latest_identity = router.get_latest_identity_event_id()
            assert latest_identity == eid2

            # Test commitment chain
            commitment_chain = router.get_commitment_chain("test123")
            assert commitment_chain == [eid3, eid4]

    def test_incremental_updates(self):
        """Test that router updates when new events are added."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))
            event_index = EventIndex(eventlog)
            router = EventRouter(eventlog, event_index)

            # Initially empty
            stats = router.get_stats()
            assert stats["indexed_events"] == 0

            # Add event after router creation
            eid = eventlog.append(
                kind="reflection", content="Added after router init", meta={}
            )

            # Router should automatically update
            updated_stats = router.get_stats()
            assert updated_stats["indexed_events"] == 1

            # Should be able to route to the new event
            query = ContextQuery(required_kinds=["reflection"], semantic_terms=[])
            results = router.route(query)
            assert results == [eid]

    def test_query_limits(self):
        """Test that query limits are respected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))

            # Add many events
            eids = []
            for i in range(10):
                eid = eventlog.append(
                    kind="reflection", content=f"Reflection {i}", meta={}
                )
                eids.append(eid)

            event_index = EventIndex(eventlog)
            router = EventRouter(eventlog, event_index)

            # Query with limit
            query = ContextQuery(
                required_kinds=["reflection"], semantic_terms=[], limit=3
            )
            results = router.route(query)

            # Should respect limit
            assert len(results) == 3
            # Should be most recent due to recency bias
            assert results == eids[-3:][::-1]  # Last 3, reversed (most recent first)

    def test_mixed_query(self):
        """Test query with both required kinds and semantic terms."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))

            # Add diverse events
            eventlog.append(
                kind="identity_adopt", content="Echo with growth mindset", meta={}
            )
            eid2 = eventlog.append(
                kind="reflection", content="Thinking about growth patterns", meta={}
            )
            eventlog.append(
                kind="commitment_open",
                content="I will focus on growth",
                meta={"cid": "growth123"},
            )
            eid4 = eventlog.append(
                kind="reflection", content="Random other thoughts", meta={}
            )

            event_index = EventIndex(eventlog)
            router = EventRouter(eventlog, event_index)

            # Query for reflections + growth-related content
            query = ContextQuery(
                required_kinds=["reflection"], semantic_terms=["growth"], limit=10
            )
            results = router.route(query)

            # Should include all reflections, but growth-related ones scored higher
            assert eid2 in results  # reflection + growth
            assert eid4 in results  # reflection only
            # eid3 might be included due to semantic match despite not being required kind

            # Growth-related reflection should be ranked higher
            growth_reflection_pos = results.index(eid2)
            other_reflection_pos = results.index(eid4)
            assert growth_reflection_pos < other_reflection_pos
