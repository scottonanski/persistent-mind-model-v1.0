"""Tests for AdaptiveReflectionCadence - only testing actual implemented code."""

import os
import tempfile

from pmm.runtime.adaptive_cadence import AdaptiveReflectionCadence
from pmm.storage.eventlog import EventLog


class TestAdaptiveReflectionCadence:
    """Test suite for AdaptiveReflectionCadence functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create temporary database for each test
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.eventlog = EventLog(self.db_path)
        self.cadence = AdaptiveReflectionCadence()

    def teardown_method(self):
        """Clean up test fixtures."""
        if hasattr(self, "eventlog"):
            self.eventlog._conn.close()
        if hasattr(self, "temp_dir"):
            import shutil

            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_hard_gate_enforcement_turn_gate(self):
        """With small turns_since_last, should_reflect returns (False, 'turn_gate')."""
        result = self.cadence.should_reflect(
            turns_since_last=1,  # Below base_min_turns=2
            seconds_since_last=100.0,  # Plenty of time
            stage="S0",
            confidence=0.5,
            base_min_turns=2,
            base_min_seconds=20.0,
            ias=[],
            gas=[],
            recent_kinds=[],
            open_commitments=0,
        )

        assert result == (False, "turn_gate")

    def test_hard_gate_enforcement_time_gate(self):
        """With small seconds_since_last, should_reflect returns (False, 'time_gate')."""
        result = self.cadence.should_reflect(
            turns_since_last=10,  # Plenty of turns
            seconds_since_last=10.0,  # Below base_min_seconds=20.0
            stage="S0",
            confidence=0.5,
            base_min_turns=2,
            base_min_seconds=20.0,
            ias=[],
            gas=[],
            recent_kinds=[],
            open_commitments=0,
        )

        assert result == (False, "time_gate")

    def test_plateau_booster(self):
        """Construct IAS/GAS sequences with tiny deltas → decision (True, 'plateau_booster')."""
        # Create sequences with tiny deltas (< 0.01)
        ias = [0.5, 0.501, 0.502, 0.503, 0.504]  # deltas: 0.001, 0.001, 0.001, 0.001
        gas = [0.6, 0.601, 0.602, 0.603, 0.604]  # deltas: 0.001, 0.001, 0.001, 0.001

        result = self.cadence.should_reflect(
            turns_since_last=10,
            seconds_since_last=100.0,
            stage="S0",
            confidence=0.5,
            base_min_turns=2,
            base_min_seconds=20.0,
            ias=ias,
            gas=gas,
            recent_kinds=[],
            open_commitments=0,
        )

        assert result == (True, "plateau_booster")

    def test_low_diversity_booster(self):
        """Provide 10 recent kinds with ≤4 unique and a run ≥4 → (True, 'low_diversity_booster')."""
        # 10 events with only 3 unique kinds and a run of 4
        recent_kinds = [
            "prompt",
            "prompt",
            "prompt",
            "prompt",
            "response",
            "response",
            "reflection",
            "prompt",
            "prompt",
            "response",
        ]
        # Unique kinds: 3 (prompt, response, reflection)
        # Diversity: 3/10 = 0.3 ≤ 0.4
        # Max run in tail 10: 4 consecutive "prompt"s at start

        result = self.cadence.should_reflect(
            turns_since_last=10,
            seconds_since_last=100.0,
            stage="S0",
            confidence=0.5,
            base_min_turns=2,
            base_min_seconds=20.0,
            ias=[],
            gas=[],
            recent_kinds=recent_kinds,
            open_commitments=0,
        )

        assert result == (True, "low_diversity_booster")

    def test_commitment_pressure(self):
        """With open_commitments >= 5 and gates passed → (True, 'commitment_pressure')."""
        result = self.cadence.should_reflect(
            turns_since_last=10,
            seconds_since_last=100.0,
            stage="S0",
            confidence=0.5,
            base_min_turns=2,
            base_min_seconds=20.0,
            ias=[],
            gas=[],
            recent_kinds=[],
            open_commitments=5,
        )

        assert result == (True, "commitment_pressure")

    def test_stage_relaxation(self):
        """With S3/S4 (and gates passed) and no other boosters → (True, 'stage_relax')."""
        for stage in ["S3", "S4"]:
            result = self.cadence.should_reflect(
                turns_since_last=10,
                seconds_since_last=100.0,
                stage=stage,
                confidence=0.5,
                base_min_turns=2,
                base_min_seconds=20.0,
                ias=[],
                gas=[],
                recent_kinds=[],
                open_commitments=0,
            )

            assert result == (True, "stage_relax")

    def test_default_ok(self):
        """Balanced inputs with gates passed and no boosters → (True, 'ok')."""
        result = self.cadence.should_reflect(
            turns_since_last=10,
            seconds_since_last=100.0,
            stage="S0",  # Not S3/S4
            confidence=0.5,
            base_min_turns=2,
            base_min_seconds=20.0,
            ias=[0.5, 0.6, 0.7],  # Not enough for plateau
            gas=[0.4, 0.5, 0.6],  # Not enough for plateau
            recent_kinds=[
                "prompt",
                "response",
                "reflection",
            ],  # Not enough for low diversity
            open_commitments=2,  # Below commitment pressure threshold
        )

        assert result == (True, "ok")

    def test_idempotent_decision_event(self):
        """maybe_emit_decision with tick_id appends exactly one; re-run → zero additional."""
        ctx = {
            "tick_id": "t1",
            "turns_since_last": 5,
            "seconds_since_last": 30.0,
            "stage": "S1",
            "confidence": 0.7,
        }
        decision = (True, "ok")

        # First emission
        event_id1 = self.cadence.maybe_emit_decision(self.eventlog, ctx, decision)
        events_after_first = len(self.eventlog.read_all())

        # Second emission with same tick_id
        event_id2 = self.cadence.maybe_emit_decision(self.eventlog, ctx, decision)
        events_after_second = len(self.eventlog.read_all())

        # First should succeed, second should be skipped
        assert event_id1 is not None
        assert event_id2 is None
        assert events_after_first == events_after_second == 1

    def test_emit_without_tick_id_always_appends(self):
        """Without tick_id, always appends."""
        ctx = {"stage": "S1", "confidence": 0.7}
        decision = (True, "ok")

        # First emission
        event_id1 = self.cadence.maybe_emit_decision(self.eventlog, ctx, decision)

        # Second emission without tick_id
        event_id2 = self.cadence.maybe_emit_decision(self.eventlog, ctx, decision)

        # Both should succeed
        assert event_id1 is not None
        assert event_id2 is not None
        assert len(self.eventlog.read_all()) == 2

    def test_metadata_compactness(self):
        """Ensure stored meta['ctx'] includes tick_id, scalars, and lengths + last values for arrays."""
        ctx = {
            "tick_id": "t1",
            "turns_since_last": 5,
            "seconds_since_last": 30.0,
            "stage": "S1",
            "confidence": 0.7,
            "ias": [0.5, 0.6, 0.7, 0.8],
            "gas": [0.4, 0.5, 0.6],
            "recent_kinds": ["prompt", "response", "reflection"],
        }
        decision = (True, "ok")

        self.cadence.maybe_emit_decision(self.eventlog, ctx, decision)

        # Get the emitted event
        events = self.eventlog.read_all()
        event = events[0]
        meta_ctx = event["meta"]["ctx"]

        # Check scalar values are preserved
        assert meta_ctx["tick_id"] == "t1"
        assert meta_ctx["turns_since_last"] == 5
        assert meta_ctx["seconds_since_last"] == 30.0
        assert meta_ctx["stage"] == "S1"
        assert meta_ctx["confidence"] == 0.7

        # Check arrays are compacted to length + last value
        assert meta_ctx["ias_length"] == 4
        assert meta_ctx["ias_last"] == 0.8
        assert meta_ctx["gas_length"] == 3
        assert meta_ctx["gas_last"] == 0.6
        assert meta_ctx["recent_kinds_length"] == 3
        assert meta_ctx["recent_kinds_last"] == "reflection"

        # Check full arrays are not stored
        assert "ias" not in meta_ctx
        assert "gas" not in meta_ctx
        assert "recent_kinds" not in meta_ctx

    def test_stage_multiplier_calculation(self):
        """Test stage multiplier calculation with confidence modulation."""
        # Test S4 with different confidence levels
        # Base multiplier for S4: 0.80

        # Low confidence (0.0): mult = 0.80 * (0.9 + 0.2*0.0) = 0.80 * 0.9 = 0.72
        result_low = self.cadence.should_reflect(
            turns_since_last=1,  # Will fail turn gate with low confidence
            seconds_since_last=100.0,
            stage="S4",
            confidence=0.0,
            base_min_turns=2,  # ceil(2 * 0.72) = ceil(1.44) = 2
            base_min_seconds=20.0,
            ias=[],
            gas=[],
            recent_kinds=[],
            open_commitments=0,
        )
        assert result_low == (False, "turn_gate")

        # High confidence (1.0): mult = 0.80 * (0.9 + 0.2*1.0) = 0.80 * 1.1 = 0.88
        result_high = self.cadence.should_reflect(
            turns_since_last=1,  # Will still fail turn gate
            seconds_since_last=100.0,
            stage="S4",
            confidence=1.0,
            base_min_turns=2,  # ceil(2 * 0.88) = ceil(1.76) = 2
            base_min_seconds=20.0,
            ias=[],
            gas=[],
            recent_kinds=[],
            open_commitments=0,
        )
        assert result_high == (False, "turn_gate")

    def test_plateau_detection_edge_cases(self):
        """Test plateau detection with various edge cases."""
        # Not enough IAS values
        result1 = self.cadence.should_reflect(
            turns_since_last=10,
            seconds_since_last=100.0,
            stage="S0",
            confidence=0.5,
            base_min_turns=2,
            base_min_seconds=20.0,
            ias=[0.5, 0.6, 0.7],  # Only 3 values, need 5
            gas=[0.4, 0.5, 0.6, 0.7, 0.8],
            recent_kinds=[],
            open_commitments=0,
        )
        assert result1 == (True, "ok")  # Falls through to default

        # Large deltas (not a plateau)
        ias_large_deltas = [0.5, 0.6, 0.7, 0.8, 0.9]  # deltas: 0.1, 0.1, 0.1, 0.1
        gas_large_deltas = [0.4, 0.5, 0.6, 0.7, 0.8]  # deltas: 0.1, 0.1, 0.1, 0.1

        result2 = self.cadence.should_reflect(
            turns_since_last=10,
            seconds_since_last=100.0,
            stage="S0",
            confidence=0.5,
            base_min_turns=2,
            base_min_seconds=20.0,
            ias=ias_large_deltas,
            gas=gas_large_deltas,
            recent_kinds=[],
            open_commitments=0,
        )
        assert result2 == (True, "ok")  # Not a plateau

    def test_low_diversity_detection_edge_cases(self):
        """Test low diversity detection with various edge cases."""
        # Not enough events
        result1 = self.cadence.should_reflect(
            turns_since_last=10,
            seconds_since_last=100.0,
            stage="S0",
            confidence=0.5,
            base_min_turns=2,
            base_min_seconds=20.0,
            ias=[],
            gas=[],
            recent_kinds=["prompt", "response"],  # Only 2 events, need 10
            open_commitments=0,
        )
        assert result1 == (True, "ok")  # Falls through to default

        # High diversity (> 0.4)
        high_diversity_kinds = [
            "a",
            "b",
            "c",
            "d",
            "e",
            "f",
            "g",
            "h",
            "i",
            "j",
        ]  # 10 unique
        result2 = self.cadence.should_reflect(
            turns_since_last=10,
            seconds_since_last=100.0,
            stage="S0",
            confidence=0.5,
            base_min_turns=2,
            base_min_seconds=20.0,
            ias=[],
            gas=[],
            recent_kinds=high_diversity_kinds,
            open_commitments=0,
        )
        assert result2 == (True, "ok")  # High diversity, not triggered

        # Low diversity but short runs
        low_diversity_short_runs = [
            "a",
            "b",
            "a",
            "b",
            "a",
            "b",
            "a",
            "b",
            "a",
            "b",
        ]  # 2 unique, max run = 1
        result3 = self.cadence.should_reflect(
            turns_since_last=10,
            seconds_since_last=100.0,
            stage="S0",
            confidence=0.5,
            base_min_turns=2,
            base_min_seconds=20.0,
            ias=[],
            gas=[],
            recent_kinds=low_diversity_short_runs,
            open_commitments=0,
        )
        assert result3 == (True, "ok")  # Low diversity but no long runs
