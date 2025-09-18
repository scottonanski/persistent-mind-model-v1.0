"""Tests for StageBehaviorManager - only testing actual implemented code."""

import tempfile
import os
from pmm.storage.eventlog import EventLog
from pmm.runtime.stage_behaviors import StageBehaviorManager


class TestStageBehaviorManager:
    """Test suite for StageBehaviorManager functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create temporary database for each test
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.eventlog = EventLog(self.db_path)
        self.manager = StageBehaviorManager()

    def teardown_method(self):
        """Clean up test fixtures."""
        if hasattr(self, "eventlog"):
            self.eventlog._conn.close()
        if hasattr(self, "temp_dir"):
            import shutil

            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_pure_adaptation_determinism(self):
        """Same inputs → identical outputs for adapt_reflection_frequency and adapt_commitment_ttl."""
        # Test reflection frequency determinism
        result1 = self.manager.adapt_reflection_frequency(1.0, "S2", 0.5)
        result2 = self.manager.adapt_reflection_frequency(1.0, "S2", 0.5)
        assert result1 == result2

        # Test commitment TTL determinism
        result3 = self.manager.adapt_commitment_ttl(10.0, "S3")
        result4 = self.manager.adapt_commitment_ttl(10.0, "S3")
        assert result3 == result4

    def test_confidence_monotonicity(self):
        """For a fixed stage, higher confidence yields ≥ multiplier within the stage band."""
        stage = "S2"
        base_freq = 1.0

        # Test increasing confidence yields non-decreasing multipliers
        conf_low = self.manager.adapt_reflection_frequency(base_freq, stage, 0.0)
        conf_mid = self.manager.adapt_reflection_frequency(base_freq, stage, 0.5)
        conf_high = self.manager.adapt_reflection_frequency(base_freq, stage, 1.0)

        assert conf_low <= conf_mid <= conf_high

    def test_stage_band_correctness(self):
        """For each stage, confidence=0 equals stage lo, confidence=1 equals stage hi."""
        base_freq = 1.0
        tolerance = 1e-9

        for stage in ["S0", "S1", "S2", "S3", "S4"]:
            lo, hi = self.manager.REFLECTION_FREQ_BANDS[stage]

            # Test confidence=0 gives lo bound
            result_lo = self.manager.adapt_reflection_frequency(base_freq, stage, 0.0)
            assert abs(result_lo - lo) < tolerance

            # Test confidence=1 gives hi bound
            result_hi = self.manager.adapt_reflection_frequency(base_freq, stage, 1.0)
            assert abs(result_hi - hi) < tolerance

    def test_reflection_frequency_clamping(self):
        """Values are clamped within [0.25, 2.0]."""
        # All stage bands should already be within bounds, but test edge cases
        for stage in ["S0", "S1", "S2", "S3", "S4"]:
            for confidence in [0.0, 0.5, 1.0]:
                result = self.manager.adapt_reflection_frequency(1.0, stage, confidence)
                assert 0.25 <= result <= 2.0

    def test_ttl_policy_correctness(self):
        """For each stage, adapt_commitment_ttl returns expected values with clamping."""
        base_ttl = 10.0
        tolerance = 1e-9
        expected_results = {
            "S0": 11.0,  # 10 * 1.10
            "S1": 10.0,  # 10 * 1.00
            "S2": 9.0,  # 10 * 0.90
            "S3": 8.0,  # 10 * 0.80
            "S4": 7.0,  # 10 * 0.70
        }

        for stage, expected in expected_results.items():
            result = self.manager.adapt_commitment_ttl(base_ttl, stage)
            assert abs(result - expected) < tolerance

    def test_ttl_clamping(self):
        """TTL multipliers are clamped to [0.5, 2.0] times base."""
        base_ttl = 10.0

        for stage in ["S0", "S1", "S2", "S3", "S4"]:
            result = self.manager.adapt_commitment_ttl(base_ttl, stage)
            # Result should be between 0.5*base and 2.0*base
            assert 0.5 * base_ttl <= result <= 2.0 * base_ttl

    def test_single_emission_on_transition(self):
        """Given an empty log, calling maybe_emit_stage_policy_update appends exactly one policy_update."""
        self.manager.maybe_emit_stage_policy_update(self.eventlog, "S1", "S2", 0.6)

        # Verify exactly one event was appended
        all_events = self.eventlog.read_all()
        assert len(all_events) == 1

        # Verify event structure
        event = all_events[0]
        assert event["kind"] == "policy_update"
        assert event["content"] == "stage behavior policy"

        meta = event["meta"]
        assert meta["component"] == "stage_behavior"
        assert meta["transition"] == {"from": "S1", "to": "S2"}
        assert meta["params"]["reflection_freq_band"] == [0.70, 1.20]  # S2 band
        assert meta["params"]["ttl_mult"] == 0.90  # S2 multiplier
        assert meta["params"]["confidence"] == 0.6
        assert meta["deterministic"] is True

    def test_idempotent_rerun(self):
        """Calling maybe_emit_stage_policy_update again with same args appends zero additional events."""
        # First call
        self.manager.maybe_emit_stage_policy_update(self.eventlog, "S1", "S2", 0.6)
        events_after_first = len(self.eventlog.read_all())

        # Second call with same arguments
        self.manager.maybe_emit_stage_policy_update(self.eventlog, "S1", "S2", 0.6)
        events_after_second = len(self.eventlog.read_all())

        # Should have same number of events
        assert events_after_first == events_after_second == 1

    def test_no_emission_when_stage_unchanged(self):
        """(prev_stage==new_stage) → no event appended."""
        # Call with same stage
        self.manager.maybe_emit_stage_policy_update(self.eventlog, "S2", "S2", 0.5)

        # Should have no events
        all_events = self.eventlog.read_all()
        assert len(all_events) == 0

    def test_multiple_different_transitions(self):
        """Multiple different transitions should each emit once."""
        # Emit S1->S2 transition
        self.manager.maybe_emit_stage_policy_update(self.eventlog, "S1", "S2", 0.6)

        # Emit S2->S3 transition
        self.manager.maybe_emit_stage_policy_update(self.eventlog, "S2", "S3", 0.7)

        # Should have two events
        all_events = self.eventlog.read_all()
        assert len(all_events) == 2

        # Verify both transitions are recorded
        transitions = []
        for event in all_events:
            if event["kind"] == "policy_update":
                transition = event["meta"]["transition"]
                transitions.append((transition["from"], transition["to"]))

        assert ("S1", "S2") in transitions
        assert ("S2", "S3") in transitions

    def test_confidence_bounds_handling(self):
        """Confidence values outside [0,1] are properly clamped."""
        # Test negative confidence
        result_neg = self.manager.adapt_reflection_frequency(1.0, "S2", -0.5)
        result_zero = self.manager.adapt_reflection_frequency(1.0, "S2", 0.0)
        assert result_neg == result_zero

        # Test confidence > 1
        result_high = self.manager.adapt_reflection_frequency(1.0, "S2", 1.5)
        result_one = self.manager.adapt_reflection_frequency(1.0, "S2", 1.0)
        assert result_high == result_one

    def test_all_stages_have_valid_bands(self):
        """All stages have valid reflection frequency bands and TTL multipliers."""
        for stage in ["S0", "S1", "S2", "S3", "S4"]:
            # Check reflection frequency bands exist and are valid
            assert stage in self.manager.REFLECTION_FREQ_BANDS
            lo, hi = self.manager.REFLECTION_FREQ_BANDS[stage]
            assert isinstance(lo, (int, float))
            assert isinstance(hi, (int, float))
            assert lo <= hi

            # Check TTL multipliers exist and are valid
            assert stage in self.manager.COMMITMENT_TTL_MULTIPLIERS
            mult = self.manager.COMMITMENT_TTL_MULTIPLIERS[stage]
            assert isinstance(mult, (int, float))
            assert mult > 0
