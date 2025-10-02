"""Tests for PatternContinuity.

Validates deterministic pattern analysis, loop detection, and idempotent
report emission according to CONTRIBUTING.md principles.
"""

from unittest.mock import Mock

from pmm.runtime.pattern_continuity import PatternContinuity


class TestPatternContinuityAnalysis:
    """Test deterministic pattern analysis from events."""

    def test_deterministic_analysis_identical_results(self):
        """Same events should produce identical analysis summaries."""
        events = [
            {
                "id": 1,
                "kind": "commitment_open",
                "meta": {"cid": "c1", "text": "Complete the task"},
            },
            {
                "id": 2,
                "kind": "reflection",
                "content": "I need to focus on completing tasks efficiently",
            },
            {"id": 3, "kind": "stage_update", "meta": {"stage": "S1"}},
        ]

        analyzer = PatternContinuity()
        summary1 = analyzer.analyze_patterns(events)
        summary2 = analyzer.analyze_patterns(events)

        assert summary1 == summary2
        assert summary1["window_size"] == 3
        assert summary1["total_events"] == 3

    def test_empty_events_returns_empty_patterns(self):
        """Empty event list should return empty patterns."""
        analyzer = PatternContinuity()
        summary = analyzer.analyze_patterns([])

        assert summary["commitment_patterns"]["total_unique_commitments"] == 0
        assert summary["reflection_patterns"]["total_reflections"] == 0
        assert summary["stage_patterns"]["total_transitions"] == 0
        assert summary["window_size"] == 0
        assert summary["total_events"] == 0

    def test_commitment_pattern_analysis(self):
        """Commitment patterns should be analyzed correctly."""
        events = [
            {
                "id": 1,
                "kind": "commitment_open",
                "meta": {"cid": "c1", "text": "Complete the task"},
            },
            {"id": 2, "kind": "commitment_close", "meta": {"cid": "c1"}},
            {
                "id": 3,
                "kind": "commitment_open",
                "meta": {"cid": "c2", "text": "Complete the task"},  # Same text
            },
            {
                "id": 4,
                "kind": "commitment_open",
                "meta": {"cid": "c3", "text": "Review the code"},
            },
        ]

        analyzer = PatternContinuity()
        summary = analyzer.analyze_patterns(events)

        cp = summary["commitment_patterns"]
        assert cp["total_unique_commitments"] == 2  # Two unique texts
        assert "complete the task" in cp["repeated_opens"]
        assert cp["repeated_opens"]["complete the task"] == 2

        # Check open/close ratios
        ratios = cp["open_close_ratios"]
        assert "complete the task" in ratios
        assert ratios["complete the task"]["opens"] == 2
        assert ratios["complete the task"]["closes"] == 1
        assert ratios["complete the task"]["ratio"] == 0.5

    def test_reflection_pattern_analysis_ngrams(self):
        """Reflection n-gram patterns should be detected."""
        events = [
            {
                "id": 1,
                "kind": "reflection",
                "content": "I need to focus on completing tasks efficiently",
            },
            {
                "id": 2,
                "kind": "reflection",
                "content": "I need to focus on improving my responses",
            },
            {
                "id": 3,
                "kind": "reflection",
                "content": "I should focus on completing tasks quickly",
            },
        ]

        analyzer = PatternContinuity()
        summary = analyzer.analyze_patterns(events)

        rp = summary["reflection_patterns"]
        assert rp["total_reflections"] == 3

        # Check for repeated n-grams
        repeated_ngrams = rp["repeated_ngrams"]
        assert "i need" in repeated_ngrams or "need to" in repeated_ngrams
        assert "to focus" in repeated_ngrams
        assert "focus on" in repeated_ngrams

    def test_stage_transition_analysis(self):
        """Stage transition patterns should be analyzed."""
        events = [
            {"id": 1, "kind": "stage_update", "meta": {"stage": "S1"}},
            {"id": 2, "kind": "stage_update", "meta": {"stage": "S2"}},
            {"id": 3, "kind": "stage_update", "meta": {"stage": "S1"}},  # Back to S1
            {
                "id": 4,
                "kind": "stage_update",
                "meta": {"stage": "S2"},  # Back to S2 again
            },
        ]

        analyzer = PatternContinuity()
        summary = analyzer.analyze_patterns(events)

        sp = summary["stage_patterns"]
        assert sp["total_transitions"] == 3  # S1->S2, S2->S1, S1->S2

        # Check for repeated transitions
        repeated_transitions = sp["repeated_transitions"]
        assert ("S1", "S2") in repeated_transitions
        assert repeated_transitions[("S1", "S2")] == 2

    def test_window_size_limits_analysis(self):
        """Window size should limit the events analyzed."""
        events = []
        for i in range(150):  # More than default window size
            events.append(
                {
                    "id": i,
                    "kind": "commitment_open",
                    "meta": {"cid": f"c{i}", "text": f"Task {i}"},
                }
            )

        analyzer = PatternContinuity(window_size=50)
        summary = analyzer.analyze_patterns(events)

        assert summary["window_size"] == 50  # Limited by window
        assert summary["total_events"] == 150  # Total count preserved
        assert summary["commitment_patterns"]["total_unique_commitments"] == 50


class TestPatternContinuityLoopDetection:
    """Test loop and anomaly detection."""

    def test_commitment_loop_detection(self):
        """Repeated commitment opens >3 times should be flagged."""
        patterns = {
            "commitment_patterns": {
                "repeated_opens": {
                    "complete the task": 5,  # Should trigger anomaly
                    "review the code": 2,  # Should not trigger
                }
            },
            "reflection_patterns": {"repeated_ngrams": {}},
            "stage_patterns": {"oscillation_sequences": [], "repeated_transitions": {}},
        }

        analyzer = PatternContinuity()
        anomalies = analyzer.detect_loops(patterns)

        assert len(anomalies) == 1
        assert "commitment_loop:5:complete the task" in anomalies[0]

    def test_reflection_ngram_loop_detection(self):
        """Repeated n-grams >5 times should be flagged."""
        patterns = {
            "commitment_patterns": {"repeated_opens": {}},
            "reflection_patterns": {
                "repeated_ngrams": {
                    "i need to": 7,  # Should trigger anomaly
                    "focus on": 3,  # Should not trigger
                }
            },
            "stage_patterns": {"oscillation_sequences": [], "repeated_transitions": {}},
        }

        analyzer = PatternContinuity()
        anomalies = analyzer.detect_loops(patterns)

        assert len(anomalies) == 1
        assert "reflection_loop:7:i need to" in anomalies[0]

    def test_stage_oscillation_detection(self):
        """Stage oscillation sequences should be flagged."""
        patterns = {
            "commitment_patterns": {"repeated_opens": {}},
            "reflection_patterns": {"repeated_ngrams": {}},
            "stage_patterns": {
                "oscillation_sequences": [[("S1", "S2"), ("S2", "S1"), ("S1", "S2")]],
                "repeated_transitions": {},
            },
        }

        analyzer = PatternContinuity()
        anomalies = analyzer.detect_loops(patterns)

        assert len(anomalies) == 1
        assert "stage_oscillation" in anomalies[0]
        assert "S1->S2" in anomalies[0]

    def test_stage_thrashing_detection(self):
        """Excessive repeated transitions >3 times should be flagged."""
        patterns = {
            "commitment_patterns": {"repeated_opens": {}},
            "reflection_patterns": {"repeated_ngrams": {}},
            "stage_patterns": {
                "oscillation_sequences": [],
                "repeated_transitions": {
                    ("S1", "S2"): 5,  # Should trigger anomaly
                    ("S2", "S3"): 2,  # Should not trigger
                },
            },
        }

        analyzer = PatternContinuity()
        anomalies = analyzer.detect_loops(patterns)

        assert len(anomalies) == 1
        assert "stage_thrashing:5:S1->S2" in anomalies[0]

    def test_no_anomalies_for_normal_patterns(self):
        """Normal patterns should not trigger anomalies."""
        patterns = {
            "commitment_patterns": {
                "repeated_opens": {
                    "complete the task": 2,  # Below threshold
                    "review the code": 1,
                }
            },
            "reflection_patterns": {
                "repeated_ngrams": {"i need to": 3, "focus on": 2}  # Below threshold
            },
            "stage_patterns": {
                "oscillation_sequences": [],
                "repeated_transitions": {("S1", "S2"): 2},  # Below threshold
            },
        }

        analyzer = PatternContinuity()
        anomalies = analyzer.detect_loops(patterns)

        assert anomalies == []


class TestPatternContinuityReportEmission:
    """Test idempotent report emission."""

    def test_maybe_emit_report_creates_event(self):
        """maybe_emit_report should create pattern_continuity_report event."""
        mock_eventlog = Mock()
        mock_eventlog.read_all.return_value = []
        mock_eventlog.append.return_value = "event_123"

        summary = {
            "commitment_patterns": {"total_unique_commitments": 5},
            "reflection_patterns": {"total_reflections": 3},
            "stage_patterns": {"total_transitions": 2},
            "window_size": 50,
            "total_events": 100,
        }

        analyzer = PatternContinuity()
        event_id = analyzer.maybe_emit_report(mock_eventlog, "src_event_42", summary)

        assert event_id == "event_123"
        mock_eventlog.append.assert_called_once()

        call_args = mock_eventlog.append.call_args
        assert call_args[1]["kind"] == "pattern_continuity_report"
        assert call_args[1]["content"] == "analysis"

        meta = call_args[1]["meta"]
        assert meta["component"] == "pattern_continuity"
        assert meta["summary"] == summary
        assert meta["src_event_id"] == "src_event_42"
        assert meta["deterministic"] is True
        assert "digest" in meta

    def test_maybe_emit_report_idempotent_skips_duplicate(self):
        """maybe_emit_report should skip if digest already exists."""
        summary = {
            "commitment_patterns": {"total_unique_commitments": 5},
            "reflection_patterns": {"total_reflections": 3},
            "stage_patterns": {"total_transitions": 2},
            "window_size": 50,
            "total_events": 100,
        }

        # Generate digest for comparison
        analyzer = PatternContinuity()
        summary_str = analyzer._serialize_summary_for_digest(summary)
        import hashlib

        digest = hashlib.sha256(summary_str.encode()).hexdigest()

        existing_events = [
            {
                "kind": "pattern_continuity_report",
                "meta": {"digest": digest},  # Same digest
            }
        ]

        mock_eventlog = Mock()
        mock_eventlog.read_all.return_value = existing_events

        event_id = analyzer.maybe_emit_report(mock_eventlog, "src_event_42", summary)

        assert event_id is None  # Should skip
        mock_eventlog.append.assert_not_called()

    def test_maybe_emit_report_emits_when_digest_differs(self):
        """maybe_emit_report should emit when digest is different."""
        existing_events = [
            {
                "kind": "pattern_continuity_report",
                "meta": {"digest": "old_digest_123"},  # Different digest
            }
        ]

        mock_eventlog = Mock()
        mock_eventlog.read_all.return_value = existing_events
        mock_eventlog.append.return_value = "event_456"

        summary = {
            "commitment_patterns": {"total_unique_commitments": 7},  # Different data
            "reflection_patterns": {"total_reflections": 5},
            "stage_patterns": {"total_transitions": 3},
            "window_size": 50,
            "total_events": 120,
        }

        analyzer = PatternContinuity()
        event_id = analyzer.maybe_emit_report(mock_eventlog, "src_event_99", summary)

        assert event_id == "event_456"
        mock_eventlog.append.assert_called_once()

    def test_deterministic_digest_generation(self):
        """Same summary should produce same digest."""
        summary = {
            "commitment_patterns": {
                "total_unique_commitments": 5,
                "repeated_opens": {"task a": 3, "task b": 2},
            },
            "reflection_patterns": {
                "total_reflections": 3,
                "repeated_ngrams": {"i need": 4, "to focus": 2},
            },
            "stage_patterns": {
                "total_transitions": 2,
                "repeated_transitions": {("S1", "S2"): 3},
            },
            "window_size": 50,
            "total_events": 100,
        }

        analyzer = PatternContinuity()
        digest1 = analyzer._serialize_summary_for_digest(summary)
        digest2 = analyzer._serialize_summary_for_digest(summary)

        assert digest1 == digest2

        # Different summary should produce different digest
        summary2 = summary.copy()
        summary2["window_size"] = 60
        digest3 = analyzer._serialize_summary_for_digest(summary2)

        assert digest1 != digest3


class TestPatternContinuityIntegration:
    """Test integration workflow and metadata integrity."""

    def test_full_workflow_analyze_detect_emit(self):
        """Test complete workflow: analyze -> detect -> emit."""
        events = [
            {
                "id": 1,
                "kind": "commitment_open",
                "meta": {"cid": "c1", "text": "Complete the task"},
            },
            {"id": 2, "kind": "commitment_close", "meta": {"cid": "c1"}},
            {
                "id": 3,
                "kind": "commitment_open",
                "meta": {"cid": "c2", "text": "Complete the task"},  # Repeat
            },
            {
                "id": 4,
                "kind": "commitment_open",
                "meta": {"cid": "c3", "text": "Complete the task"},  # Repeat
            },
            {
                "id": 5,
                "kind": "commitment_open",
                "meta": {"cid": "c4", "text": "Complete the task"},  # Repeat
            },
            {
                "id": 6,
                "kind": "commitment_open",
                "meta": {
                    "cid": "c5",
                    "text": "Complete the task",
                },  # 5th repeat - should trigger anomaly
            },
        ]

        mock_eventlog = Mock()
        mock_eventlog.read_all.return_value = []
        mock_eventlog.append.return_value = "report_event_123"

        analyzer = PatternContinuity()

        # Analyze patterns
        summary = analyzer.analyze_patterns(events)
        assert (
            summary["commitment_patterns"]["repeated_opens"]["complete the task"] == 5
        )

        # Detect loops
        anomalies = analyzer.detect_loops(summary)
        assert len(anomalies) == 1
        assert "commitment_loop:5" in anomalies[0]

        # Emit report
        event_id = analyzer.maybe_emit_report(mock_eventlog, "trigger_event_6", summary)
        assert event_id == "report_event_123"

        # Verify report metadata
        call_args = mock_eventlog.append.call_args
        meta = call_args[1]["meta"]
        assert meta["component"] == "pattern_continuity"
        assert meta["src_event_id"] == "trigger_event_6"
        assert meta["deterministic"] is True
        assert meta["window_size"] == 6
        assert meta["total_events"] == 6

    def test_metadata_integrity_preservation(self):
        """Metadata should be preserved correctly in reports."""
        events = [
            {
                "id": 10,
                "kind": "reflection",
                "content": "I need to focus on completing tasks efficiently",
            },
            {"id": 11, "kind": "stage_update", "meta": {"stage": "S2"}},
        ]

        mock_eventlog = Mock()
        mock_eventlog.read_all.return_value = []
        mock_eventlog.append.return_value = "report_event_456"

        analyzer = PatternContinuity()
        summary = analyzer.analyze_patterns(events)

        analyzer.maybe_emit_report(mock_eventlog, "trigger_event_11", summary)

        call_args = mock_eventlog.append.call_args
        meta = call_args[1]["meta"]

        # Verify all required metadata fields
        assert meta["component"] == "pattern_continuity"
        assert meta["src_event_id"] == "trigger_event_11"
        assert meta["deterministic"] is True
        assert "digest" in meta
        assert meta["window_size"] == 2
        assert meta["total_events"] == 2
        assert "summary" in meta

        # Verify summary structure
        summary_meta = meta["summary"]
        assert "commitment_patterns" in summary_meta
        assert "reflection_patterns" in summary_meta
        assert "stage_patterns" in summary_meta
