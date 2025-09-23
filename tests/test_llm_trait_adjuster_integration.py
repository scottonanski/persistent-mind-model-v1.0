"""
Integration tests for LLM-driven trait adjustment system.
Tests end-to-end flow from LLM response to trait_update events.
"""

import tempfile
import os

from pmm.storage.eventlog import EventLog
from pmm.runtime.llm_trait_adjuster import apply_llm_trait_adjustments


class TestLLMTraitAdjusterIntegration:
    """Integration tests for LLM trait adjustment system."""

    def test_llm_trait_adjuster_creates_trait_update_event(self, monkeypatch):
        """Test that valid LLM suggestions result in trait_update events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "events.db")
            eventlog = EventLog(db_path)

            # Fake LLM response that should parse as a valid suggestion
            llm_response = "I should increase my openness by 0.03 because this conversation was creative."

            # Ensure trait adjustments are enabled
            monkeypatch.setenv("PMM_LLM_TRAIT_ADJUSTMENTS", "1")

            applied_event_ids = apply_llm_trait_adjustments(eventlog, llm_response)

            # We expect exactly one adjustment event
            assert len(applied_event_ids) == 1

            event_id = applied_event_ids[0]
            events = eventlog.read_all()
            ev = next(e for e in events if e["id"] == event_id)
            assert ev["kind"] == "trait_update"
            assert "delta" in ev["meta"]
            assert "O" in ev["meta"]["delta"]
            assert abs(ev["meta"]["delta"]["O"] - 0.03) < 1e-6
            assert ev["meta"]["reason"] == "llm_suggestion"
            assert ev["meta"]["source"] == "llm_trait_adjuster"

            # The event should now be stored in the ledger
            events = eventlog.read_all()
            trait_updates = [e for e in events if e["kind"] == "trait_update"]
            assert len(trait_updates) == 1
            assert trait_updates[0]["meta"]["delta"]["O"] == 0.03

    def test_llm_trait_adjuster_rejects_out_of_bounds(self, monkeypatch):
        """Test that out-of-bounds suggestions are rejected and logged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "events.db")
            eventlog = EventLog(db_path)

            # Fake LLM response suggesting an invalid trait jump
            llm_response = (
                "I should increase my openness by 2.0 because I'm super creative."
            )

            # Enable adjuster
            monkeypatch.setenv("PMM_LLM_TRAIT_ADJUSTMENTS", "1")

            applied_event_ids = apply_llm_trait_adjustments(eventlog, llm_response)

            # Nothing should be applied
            assert applied_event_ids == []

            # Event log should contain a rejection event instead
            events = eventlog.read_all()
            rejections = [e for e in events if e["kind"] == "trait_adjustment_rejected"]

            assert len(rejections) == 1
            meta = rejections[0]["meta"]

            # Sanity check rejection metadata
            assert meta["source"] == "llm_trait_adjuster"
            assert "reason" in meta
            assert "confidence" in meta["suggestion"]

    def test_llm_trait_adjuster_respects_rate_limit(self, monkeypatch):
        """Test that rate limiting prevents multiple adjustments per conversation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "events.db")
            eventlog = EventLog(db_path)

            # Two valid suggestions in one "conversation"
            llm_response = (
                "I should increase my openness by 0.02 because this was creative. "
                "I should also increase my conscientiousness by 0.01 since I finished tasks."
            )

            # Enable adjuster and enforce 1 adjustment per conversation
            monkeypatch.setenv("PMM_LLM_TRAIT_ADJUSTMENTS", "1")
            monkeypatch.setenv("PMM_LLM_TRAIT_MAX_PER_CONVERSATION", "1")

            applied_event_ids = apply_llm_trait_adjustments(eventlog, llm_response)

            # Only one event should be applied due to rate limiting
            assert len(applied_event_ids) == 1
            # Read the event to verify it
            events = eventlog.read_all()
            event_id = applied_event_ids[0]
            ev = next(e for e in events if e["id"] == event_id)
            assert ev["kind"] == "trait_update"

            # Read back all events
            events = eventlog.read_all()
            trait_updates = [e for e in events if e["kind"] == "trait_update"]
            rejections = [e for e in events if e["kind"] == "trait_adjustment_rejected"]

            # Exactly one update and at least one rejection
            assert len(trait_updates) == 1
            assert len(rejections) >= 1

            # Verify rejection is clearly due to rate limit
            assert any(
                "conversation" in r["meta"]["reason"].lower()
                or "max" in r["meta"]["reason"].lower()
                for r in rejections
            )


class TestLLMTraitAdjusterUnit:
    """Unit tests for individual components."""

    def test_parsing_edge_cases(self):
        """Test parsing handles various edge cases correctly."""
        from pmm.runtime.llm_trait_adjuster import LLMTraitAdjuster

        adjuster = LLMTraitAdjuster()

        test_cases = [
            # Valid cases
            ("I should increase openness by 0.05", True),
            ("I recommend decreasing neuroticism by 0.02", True),
            ("Maybe I could adjust conscientiousness", False),  # No number, too vague
            ("I should increase my O by 0.03", True),  # Short form
            ("", False),  # Empty
            (
                "I should increase openness by 2.5",
                True,
            ),  # Parses but rejected by bounds check
        ]

        for text, should_parse in test_cases:
            suggestions = adjuster.parse_trait_suggestions(text)
            if should_parse:
                assert len(suggestions) > 0, f"Should parse: {text}"
            else:
                assert len(suggestions) == 0, f"Should not parse: {text}"

    def test_confidence_scoring(self):
        """Test confidence estimation works correctly."""
        from pmm.runtime.llm_trait_adjuster import LLMTraitAdjuster

        adjuster = LLMTraitAdjuster()

        # High confidence case
        high_conf = adjuster._estimate_confidence(
            "should increase openness by 0.03",
            "I should increase openness by 0.03 because this was creative and innovative.",
        )
        assert high_conf >= 0.7

        # Low confidence case
        low_conf = adjuster._estimate_confidence(
            "maybe increase openness", "Maybe I could increase openness a bit."
        )
        assert low_conf <= 0.6

    def test_validation_bounds(self):
        """Test bounds checking works correctly."""
        from pmm.runtime.llm_trait_adjuster import LLMTraitAdjuster

        adjuster = LLMTraitAdjuster()

        # Valid suggestion
        valid = {
            "trait": "O",
            "delta": 0.03,
            "confidence": 0.8,
            "context": "increase openness by 0.03",
        }
        current_values = {"O": 0.96, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5}
        is_valid, reason = adjuster.validate_suggestion(valid, current_values)
        assert is_valid
        assert reason == "Valid"

        # Invalid: too large delta
        invalid_large = valid.copy()
        invalid_large["delta"] = 0.2  # Over max_delta_per_adjustment (0.05)
        is_valid, reason = adjuster.validate_suggestion(invalid_large, current_values)
        assert not is_valid
        assert "too large" in reason

        # Invalid: would exceed upper bound
        invalid_bounds = valid.copy()
        invalid_bounds["delta"] = 0.05  # 0.96 + 0.05 = 1.01 > 1.0
        is_valid, reason = adjuster.validate_suggestion(invalid_bounds, current_values)
        assert not is_valid
        assert "too high" in reason

        # Invalid: low confidence
        invalid_conf = valid.copy()
        invalid_conf["confidence"] = 0.4  # Below threshold (0.6)
        is_valid, reason = adjuster.validate_suggestion(invalid_conf, current_values)
        assert not is_valid
        assert "Low confidence" in reason
