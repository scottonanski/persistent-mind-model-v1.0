"""Tests for TraitDriftManager - only testing actual implemented code."""

import json
import os
import tempfile

from pmm.personality.self_evolution import TraitDriftManager
from pmm.storage.eventlog import EventLog


class TestTraitDriftManager:
    """Test suite for TraitDriftManager functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create temporary database for each test
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.eventlog = EventLog(self.db_path)
        self.manager = TraitDriftManager()

    def teardown_method(self):
        """Clean up test fixtures."""
        if hasattr(self, "eventlog"):
            self.eventlog._conn.close()
        if hasattr(self, "temp_dir"):
            import shutil

            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_appends_once(self):
        """Given a seeded event and empty log, apply_and_log appends exactly one policy_update."""
        # Create a test event that should trigger trait changes
        test_event = {
            "id": 1,
            "kind": "prompt",
            "content": "I want to explore and learn about new technologies",
            "meta": {},
        }
        context = {}

        # Apply and log
        self.manager.apply_and_log(self.eventlog, test_event, context)

        # Verify exactly one policy_update was appended
        all_events = self.eventlog.read_all()
        policy_updates = [e for e in all_events if e["kind"] == "policy_update"]
        assert len(policy_updates) == 1

        # Verify the policy_update has correct structure
        update = policy_updates[0]
        assert update["content"] == "trait drift update"
        assert update["meta"]["component"] == "personality"
        assert update["meta"]["source_event_id"] == 1
        assert len(update["meta"]["changes"]) > 0
        assert update["meta"]["deterministic"] is True
        assert "embedding_spec" in update["meta"]

    def test_idempotent_rerun(self):
        """Running again with the same inputs appends zero additional events."""
        # Create test event
        test_event = {
            "id": 1,
            "kind": "prompt",
            "content": "I want to explore and learn about new technologies",
            "meta": {},
        }
        context = {}

        # First run
        self.manager.apply_and_log(self.eventlog, test_event, context)
        events_after_first = len(self.eventlog.read_all())

        # Second run with same inputs
        self.manager.apply_and_log(self.eventlog, test_event, context)
        events_after_second = len(self.eventlog.read_all())

        # Should have same number of events (no additional append)
        assert events_after_first == events_after_second

    def test_deterministic(self):
        """Two fresh logs, same inputs → byte-equal meta['changes']."""
        # Create test event
        test_event = {
            "id": 1,
            "kind": "prompt",
            "content": "I want to plan and organize my work schedule",
            "meta": {},
        }
        context = {}

        # First log
        log1 = EventLog(os.path.join(self.temp_dir, "log1.db"))
        manager1 = TraitDriftManager()
        manager1.apply_and_log(log1, test_event, context)
        events1 = log1.read_all()
        changes1 = events1[0]["meta"]["changes"]
        log1._conn.close()

        # Second log
        log2 = EventLog(os.path.join(self.temp_dir, "log2.db"))
        manager2 = TraitDriftManager()
        manager2.apply_and_log(log2, test_event, context)
        events2 = log2.read_all()
        changes2 = events2[0]["meta"]["changes"]
        log2._conn.close()

        # Serialize and compare
        changes1_json = json.dumps(changes1, sort_keys=True)
        changes2_json = json.dumps(changes2, sort_keys=True)
        assert changes1_json == changes2_json

    def test_integrity(self):
        """Each change has trait in {'O','C','E','A','N'} and finite delta in [-1.0, 1.0]."""
        # Create test event that triggers multiple trait changes
        test_event = {
            "id": 1,
            "kind": "prompt",
            "content": "I want to explore new ideas, plan carefully, and help others collaborate",
            "meta": {},
        }
        context = {}

        # Get trait deltas directly
        deltas = self.manager.apply_event_effects(test_event, context)

        # Verify each delta meets constraints
        for delta in deltas:
            assert "trait" in delta
            assert "delta" in delta
            assert delta["trait"] in {"O", "C", "E", "A", "N"}
            assert isinstance(delta["delta"], (int, float))
            assert -1.0 <= delta["delta"] <= 1.0
            assert abs(delta["delta"]) != float("inf")
            assert delta["delta"] == delta["delta"]  # Not NaN

    def test_metadata_completeness(self):
        """Meta contains component, source_event_id, changes, deterministic, and embedding_spec."""
        test_event = {
            "id": 42,
            "kind": "prompt",
            "content": "I need to learn something new",
            "meta": {},
        }
        context = {}

        self.manager.apply_and_log(self.eventlog, test_event, context)

        # Get the policy_update event
        all_events = self.eventlog.read_all()
        policy_update = next(e for e in all_events if e["kind"] == "policy_update")
        meta = policy_update["meta"]

        # Verify all required keys are present
        assert "component" in meta
        assert "source_event_id" in meta
        assert "changes" in meta
        assert "deterministic" in meta
        assert "embedding_spec" in meta

        # Verify values
        assert meta["component"] == "personality"
        assert meta["source_event_id"] == 42
        assert isinstance(meta["changes"], list)
        assert len(meta["changes"]) > 0
        assert meta["deterministic"] is True
        assert isinstance(meta["embedding_spec"], dict)

    def test_no_changes_no_event(self):
        """If apply_event_effects returns empty list, no policy_update is appended."""
        # Create event that should not trigger any trait changes
        test_event = {
            "id": 1,
            "kind": "system",
            "content": "neutral system message",
            "meta": {},
        }
        context = {}

        self.manager.apply_and_log(self.eventlog, test_event, context)

        # Should have no events in log
        all_events = self.eventlog.read_all()
        assert len(all_events) == 0

    def test_apply_event_effects_direct(self):
        """Test apply_event_effects method directly for various event types."""
        # Test curiosity-indicating event
        curiosity_event = {
            "kind": "prompt",
            "content": "I want to explore new possibilities",
            "meta": {},
        }
        deltas = self.manager.apply_event_effects(curiosity_event, {})
        openness_deltas = [d for d in deltas if d["trait"] == "O"]
        assert len(openness_deltas) > 0
        assert openness_deltas[0]["delta"] > 0

        # Test planning-indicating event
        planning_event = {
            "kind": "prompt",
            "content": "I need to organize and plan my approach",
            "meta": {},
        }
        deltas = self.manager.apply_event_effects(planning_event, {})
        conscientiousness_deltas = [d for d in deltas if d["trait"] == "C"]
        assert len(conscientiousness_deltas) > 0
        assert conscientiousness_deltas[0]["delta"] > 0

    def test_valid_traits_only(self):
        """Verify only valid Big Five traits are used."""
        test_event = {
            "kind": "prompt",
            "content": (
                "comprehensive test content with explore, plan, "
                "collaborate, help, and calm words"
            ),
            "meta": {},
        }

        deltas = self.manager.apply_event_effects(test_event, {})

        for delta in deltas:
            assert delta["trait"] in TraitDriftManager.VALID_TRAITS
