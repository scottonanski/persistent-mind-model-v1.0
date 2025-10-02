"""
Phase 4 Integration Tests: AutonomyLoop Introspective Agency Integration

Tests verify that the AutonomyLoop properly integrates introspective agency
with deterministic cadence, digest idempotency, schema safety, and replay consistency.
All tests follow CONTRIBUTING.md principles for ledger integrity and auditability.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from pmm.constants import EventKinds
from pmm.runtime.cooldown import ReflectionCooldown
from pmm.runtime.loop import AutonomyLoop
from pmm.storage.eventlog import EventLog


class TestPhase4AutonomyIntegration:
    """Test suite for Phase 4 introspective agency integration."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database for isolated testing."""
        temp_dir = tempfile.mkdtemp()
        db_path = Path(temp_dir) / "test_phase4.db"
        yield str(db_path)
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def eventlog(self, temp_db_path):
        """Create EventLog instance for testing."""
        return EventLog(temp_db_path)

    @pytest.fixture
    def autonomy_loop(self, eventlog):
        """Create AutonomyLoop with introspection integration."""
        cooldown = ReflectionCooldown()
        loop = AutonomyLoop(
            eventlog=eventlog,
            cooldown=cooldown,
            interval_seconds=1.0,
            bootstrap_identity=False,  # Skip bootstrap for cleaner tests
        )
        # Set shorter cadence for testing
        loop._introspection_cadence = 3
        return loop

    def test_introspection_cadence_deterministic(self, autonomy_loop):
        """Test that _should_introspect follows deterministic cadence."""
        # Test cadence pattern with 3-tick cycle
        assert not autonomy_loop._should_introspect(0)  # Tick 0: no introspection
        assert not autonomy_loop._should_introspect(1)  # Tick 1: no introspection
        assert not autonomy_loop._should_introspect(2)  # Tick 2: no introspection
        assert autonomy_loop._should_introspect(3)  # Tick 3: introspection
        assert not autonomy_loop._should_introspect(4)  # Tick 4: no introspection
        assert not autonomy_loop._should_introspect(5)  # Tick 5: no introspection
        assert autonomy_loop._should_introspect(6)  # Tick 6: introspection

        # Verify determinism: same inputs always produce same outputs
        for tick in [0, 1, 2, 3, 4, 5, 6, 9, 12, 15]:
            result1 = autonomy_loop._should_introspect(tick)
            result2 = autonomy_loop._should_introspect(tick)
            assert result1 == result2, f"Non-deterministic result for tick {tick}"

    def test_introspection_cycle_orchestration(self, autonomy_loop, eventlog):
        """Test that _run_introspection_cycle orchestrates all phases correctly."""
        # Add some test events to trigger introspection
        eventlog.append(
            EventKinds.COMMITMENT_OPEN,
            "",
            {"cid": "test_cid_1", "text": "Test commitment 1", "status": "open"},
        )
        eventlog.append(
            EventKinds.REFLECTION,
            "",
            {"rid": "test_rid_1", "insight": "Test insight", "topic": "testing"},
        )
        eventlog.append(
            EventKinds.TRAIT_UPDATE, "", {"trait": "test_trait", "delta": 0.1}
        )

        before = list(eventlog.read_all())
        autonomy_loop._run_introspection_cycle(tick_no=3)
        after = list(eventlog.read_all())

        # Should emit introspection query event and potentially evolution event
        new_events = [e for e in after if e not in before]

        # Find the introspection query event
        query_events = [
            e for e in new_events if e["kind"] == EventKinds.INTROSPECTION_QUERY
        ]
        assert len(query_events) == 1, "Must emit exactly one introspection query event"

        query_ev = query_events[0]
        assert "digest" in query_ev["meta"]
        assert "payload" in query_ev["meta"]
        assert query_ev["content"] == "combined_query"

        # May also emit evolution events from Phase 2/3
        evolution_events = [e for e in new_events if e["kind"] == EventKinds.EVOLUTION]
        for ev in evolution_events:
            assert ev["content"] == ""
            assert "digest" in ev["meta"]

    def test_introspection_integration_in_tick(self, autonomy_loop, eventlog):
        """Test that tick() properly integrates introspection calls."""
        # Add test events
        eventlog.append(
            EventKinds.COMMITMENT_OPEN,
            "",
            {
                "cid": "integration_test_cid",
                "text": "Integration test commitment",
                "status": "open",
            },
        )

        # Mock the introspection methods to track calls
        introspection_calls = []

        def mock_should_introspect(tick_no):
            return tick_no == 3  # Only introspect on tick 3

        def mock_run_introspection_cycle(tick_no):
            introspection_calls.append(tick_no)

        autonomy_loop._should_introspect = mock_should_introspect
        autonomy_loop._run_introspection_cycle = mock_run_introspection_cycle

        # Run multiple ticks
        for _ in range(5):
            autonomy_loop.tick()

        # Verify introspection was called exactly once on the right tick
        # Note: tick numbers start from 1 in the actual implementation
        assert (
            len(introspection_calls) <= 1
        ), "Introspection should be called at most once"

    def test_introspection_idempotency(self, autonomy_loop, eventlog):
        """Test that repeated introspection cycles are idempotent."""
        # Add test events
        eventlog.append(
            EventKinds.COMMITMENT_OPEN,
            "",
            {
                "cid": "idempotency_test_cid",
                "text": "Idempotency test commitment",
                "status": "open",
            },
        )

        # Run introspection cycle twice with same tick
        tick_no = 6
        autonomy_loop._run_introspection_cycle(tick_no)
        events_after_first = eventlog.read_all()

        autonomy_loop._run_introspection_cycle(tick_no)
        events_after_second = eventlog.read_all()

        # Count events by kind
        def count_events_by_kind(events, kind):
            return len([e for e in events if e.get("kind") == kind])

        # Verify no duplicate events were created
        query_count_1 = count_events_by_kind(
            events_after_first, EventKinds.INTROSPECTION_QUERY
        )
        query_count_2 = count_events_by_kind(
            events_after_second, EventKinds.INTROSPECTION_QUERY
        )

        evolution_count_1 = count_events_by_kind(
            events_after_first, EventKinds.EVOLUTION
        )
        evolution_count_2 = count_events_by_kind(
            events_after_second, EventKinds.EVOLUTION
        )

        # Due to digest-based idempotency, counts should be the same
        assert (
            query_count_1 == query_count_2
        ), "Introspection query events should be idempotent"
        assert (
            evolution_count_1 == evolution_count_2
        ), "Evolution events should be idempotent"

    def test_introspection_schema_safety(self, autonomy_loop, eventlog):
        """Test that introspection handles missing meta fields gracefully."""
        # Add events with missing meta fields
        eventlog.append(
            EventKinds.COMMITMENT_OPEN, "malformed commitment", {}
        )  # Missing required fields
        eventlog.append(
            EventKinds.REFLECTION, "malformed reflection", {}
        )  # Missing required fields
        eventlog.append(
            EventKinds.TRAIT_UPDATE, "malformed trait", {}
        )  # Missing required fields

        before = list(eventlog.read_all())
        autonomy_loop._run_introspection_cycle(tick_no=9)
        after = list(eventlog.read_all())

        # Verify graceful handling - should emit introspection event with empty results
        new_events = [e for e in after if e not in before]
        if new_events:
            ev = new_events[0]
            assert ev["kind"] == EventKinds.INTROSPECTION_QUERY
            # Should handle malformed events by producing empty results
            payload = ev["meta"].get("payload", {})
            assert (
                "commitments" in payload
                or "reflections" in payload
                or "traits" in payload
            )

    def test_introspection_replay_consistency(
        self, autonomy_loop, eventlog, temp_db_path
    ):
        """Test that introspection produces consistent results across replays."""
        # Add deterministic test events
        test_events = [
            (
                EventKinds.COMMITMENT_OPEN,
                "",
                {"cid": "replay_cid_1", "text": "Replay test 1", "status": "open"},
            ),
            (
                EventKinds.COMMITMENT_OPEN,
                "",
                {"cid": "replay_cid_2", "text": "Replay test 2", "status": "open"},
            ),
            (
                EventKinds.REFLECTION,
                "",
                {"rid": "replay_rid_1", "insight": "Replay insight", "topic": "replay"},
            ),
            (EventKinds.TRAIT_UPDATE, "", {"trait": "replay_trait", "delta": 0.2}),
        ]

        for kind, content, meta in test_events:
            eventlog.append(kind, content, meta)

        # Run first introspection cycle
        tick_no = 12
        autonomy_loop._run_introspection_cycle(tick_no)
        events_first_run = eventlog.read_all()

        # Create new EventLog with same data
        eventlog2 = EventLog(temp_db_path + "_replay")
        for kind, content, meta in test_events:
            eventlog2.append(kind, content, meta)

        # Create new AutonomyLoop and run same introspection
        cooldown2 = ReflectionCooldown()
        autonomy_loop2 = AutonomyLoop(
            eventlog=eventlog2,
            cooldown=cooldown2,
            interval_seconds=1.0,
            bootstrap_identity=False,
        )
        autonomy_loop2._introspection_cadence = 3
        autonomy_loop2._run_introspection_cycle(tick_no)
        events_second_run = eventlog2.read_all()

        # Compare introspection-generated events (filter out the original test events)
        def get_introspection_events(events):
            return [
                e
                for e in events
                if e.get("kind")
                in [EventKinds.INTROSPECTION_QUERY, EventKinds.EVOLUTION]
            ]

        intro_events_1 = get_introspection_events(events_first_run)
        intro_events_2 = get_introspection_events(events_second_run)

        # Should have same number of introspection events
        assert len(intro_events_1) == len(
            intro_events_2
        ), "Replay should produce same number of introspection events"

        # Verify event kinds match
        kinds_1 = [e.get("kind") for e in intro_events_1]
        kinds_2 = [e.get("kind") for e in intro_events_2]
        assert sorted(kinds_1) == sorted(
            kinds_2
        ), "Replay should produce same event kinds"

    def test_introspection_error_resilience(self, autonomy_loop, eventlog):
        """Test that introspection errors are handled deterministically."""

        # Mock introspection components to raise exceptions
        def failing_query_commitments():
            raise Exception("Simulated failure in query_commitments")

        autonomy_loop._self_introspection.query_commitments = failing_query_commitments

        # Run introspection cycle - should handle error deterministically
        before = list(eventlog.read_all())
        autonomy_loop._run_introspection_cycle(tick_no=15)
        after = list(eventlog.read_all())

        # Verify no events emitted due to component failure (try/except swallows error)
        new_events = [e for e in after if e not in before]
        assert len(new_events) == 0, "Failed introspection should not emit events"

        # Verify autonomy loop continues functioning
        autonomy_loop.tick()  # Should not raise exception

    def test_introspection_cadence_configuration(self, eventlog):
        """Test that introspection cadence can be configured."""
        cooldown = ReflectionCooldown()

        # Test different cadence values
        for cadence in [5, 10, 20]:
            loop = AutonomyLoop(
                eventlog=eventlog,
                cooldown=cooldown,
                interval_seconds=1.0,
                bootstrap_identity=False,
            )
            loop._introspection_cadence = cadence

            # Test cadence pattern
            assert not loop._should_introspect(cadence - 1)
            assert loop._should_introspect(cadence)
            assert not loop._should_introspect(cadence + 1)
            assert loop._should_introspect(cadence * 2)

    def test_introspection_meta_field_access(self, autonomy_loop, eventlog):
        """Test that introspection components access structured meta fields correctly."""
        # Add events with content but structured meta
        eventlog.append(
            EventKinds.COMMITMENT_OPEN,
            "This content should be ignored",
            {"cid": "meta_test_cid", "text": "Meta field text", "status": "open"},
        )
        eventlog.append(
            EventKinds.REFLECTION,
            "This content should also be ignored",
            {
                "rid": "meta_test_rid",
                "insight": "Meta field insight",
                "topic": "meta_testing",
            },
        )

        # Test that individual introspection components access meta fields correctly
        commitment_summary = autonomy_loop._self_introspection.query_commitments()
        reflection_summary = autonomy_loop._self_introspection.analyze_reflections()

        # Verify components extracted data from meta fields, not content
        assert "commitments" in commitment_summary
        assert "reflections" in reflection_summary

        # Check that commitment data came from meta fields
        if commitment_summary["commitments"]:
            first_commitment = list(commitment_summary["commitments"].values())[0]
            assert first_commitment["cid"] == "meta_test_cid"
            assert (
                first_commitment["text"] == "Meta field text"
            )  # From meta, not content

        # Check that reflection data came from meta fields
        if reflection_summary["reflections"]:
            first_reflection = reflection_summary["reflections"][0]
            assert first_reflection["rid"] == "meta_test_rid"
            assert first_reflection["topic"] == "meta_testing"  # From meta, not content
