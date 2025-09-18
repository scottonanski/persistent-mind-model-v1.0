"""Tests for MetaReflection class.

Comprehensive test suite covering deterministic reflection analysis, bias detection,
idempotent event emission, and CONTRIBUTING.md compliance.
"""

from pmm.runtime.meta.meta_reflection import MetaReflection


class MockEventLog:
    """Mock event log for testing."""

    def __init__(self):
        self.events = []
        self.next_id = 1

    def append(self, kind: str, content: str, meta: dict) -> str:
        event_id = f"event_{self.next_id}"
        self.next_id += 1
        event = {"id": event_id, "kind": kind, "content": content, "meta": meta}
        self.events.append(event)
        return event_id

    def read_all(self):
        return self.events


def test_analyze_reflections_empty():
    """Test reflection analysis with empty/invalid inputs."""
    meta_reflection = MetaReflection()

    # Empty list
    result = meta_reflection.analyze_reflections([])
    assert result["reflection_count"] == 0
    assert result["bias_metrics"]["stance_skew"] == 0.0
    assert result["depth_metrics"]["depth_score"] == 0.0

    # None input
    result = meta_reflection.analyze_reflections(None)
    assert result["reflection_count"] == 0

    # List with non-dict items
    result = meta_reflection.analyze_reflections(["invalid", None, 123])
    assert result["reflection_count"] == 0


def test_analyze_reflections_no_reflections():
    """Test analysis with events that contain no reflection events."""
    meta_reflection = MetaReflection()

    events = [
        {"id": "e1", "kind": "commitment_open", "content": "I will exercise"},
        {"id": "e2", "kind": "policy_update", "content": "Updated policy"},
        {"id": "e3", "kind": "stage_update", "content": "Stage changed"},
    ]

    result = meta_reflection.analyze_reflections(events)
    assert result["reflection_count"] == 0
    assert result["bias_metrics"]["stance_skew"] == 0.0


def test_analyze_reflections_basic():
    """Test basic reflection analysis with mixed stance content."""
    meta_reflection = MetaReflection()

    events = [
        {
            "id": "r1",
            "kind": "reflection",
            "content": "I feel great about my progress today. Everything went well and I'm happy with the results.",
        },
        {
            "id": "r2",
            "kind": "reflection",
            "content": "This was a terrible day. I failed at everything and feel frustrated with my performance.",
        },
        {
            "id": "r3",
            "kind": "reflection",
            "content": "Today was okay, nothing special. Just a normal day with average results.",
        },
    ]

    result = meta_reflection.analyze_reflections(events)

    assert result["reflection_count"] == 3

    # Check bias metrics
    bias_metrics = result["bias_metrics"]
    assert bias_metrics["positive_ratio"] > 0.0
    assert bias_metrics["negative_ratio"] > 0.0
    assert bias_metrics["neutral_ratio"] > 0.0
    assert 0.0 <= bias_metrics["stance_skew"] <= 1.0


def test_analyze_reflections_bias_detection():
    """Test bias detection with heavily skewed content."""
    meta_reflection = MetaReflection()

    # All positive reflections
    positive_events = [
        {
            "id": "r1",
            "kind": "reflection",
            "content": "Great day! Excellent progress and wonderful results.",
        },
        {
            "id": "r2",
            "kind": "reflection",
            "content": "Amazing work today. Fantastic achievements and successful outcomes.",
        },
        {
            "id": "r3",
            "kind": "reflection",
            "content": "Outstanding performance. Proud of my accomplishments and excited for tomorrow.",
        },
    ]

    result = meta_reflection.analyze_reflections(positive_events)

    bias_metrics = result["bias_metrics"]
    assert bias_metrics["positive_ratio"] > 0.8  # Should be heavily positive
    assert bias_metrics["stance_skew"] > 0.5  # Should show significant skew


def test_analyze_reflections_depth_analysis():
    """Test depth analysis with shallow vs deep reflections."""
    meta_reflection = MetaReflection()

    events = [
        {
            "id": "r1",
            "kind": "reflection",
            "content": "Just a quick update. Obviously everything is fine. Simply moving forward.",
        },
        {
            "id": "r2",
            "kind": "reflection",
            "content": "Today I engaged in a comprehensive analysis of my underlying motivations and the complex interconnected factors that influence my decision-making process. The nuanced implications of my actions reveal profound insights into the fundamental patterns that shape my behavior and the sophisticated mechanisms through which I can achieve more meaningful outcomes.",
        },
    ]

    result = meta_reflection.analyze_reflections(events)

    depth_metrics = result["depth_metrics"]
    assert depth_metrics["avg_token_length"] > 0.0
    assert depth_metrics["shallow_ratio"] > 0.0  # Should detect shallow indicators
    assert depth_metrics["deep_ratio"] > 0.0  # Should detect deep indicators


def test_analyze_reflections_closure_patterns():
    """Test closure pattern analysis with commitment references."""
    meta_reflection = MetaReflection()

    reflection_events = [
        {
            "id": "r1",
            "kind": "reflection",
            "content": "Reflecting on my commitment to exercise. I completed my goal and accomplished what I set out to do.",
        },
        {
            "id": "r2",
            "kind": "reflection",
            "content": "My promise to read more books is going well. I finished another chapter and learned something new.",
        },
    ]

    # Include some commitment events for context
    all_events = reflection_events + [
        {"id": "c1", "kind": "commitment_open", "content": "I will exercise daily"},
        {
            "id": "c2",
            "kind": "commitment_close",
            "content": "Exercise commitment completed",
        },
    ]

    result = meta_reflection.analyze_reflections(all_events)

    closure_metrics = result["closure_metrics"]
    assert closure_metrics["commitment_mentions"] >= 2
    assert closure_metrics["follow_through_ratio"] > 0.0
    assert closure_metrics["evolution_indicators"] > 0


def test_analyze_reflections_repetition_patterns():
    """Test repetition and diversity analysis."""
    meta_reflection = MetaReflection()

    # Repetitive reflections
    repetitive_events = [
        {
            "id": "r1",
            "kind": "reflection",
            "content": "Today I worked on my project and made progress.",
        },
        {
            "id": "r2",
            "kind": "reflection",
            "content": "Today I worked on my project and made progress.",
        },
        {
            "id": "r3",
            "kind": "reflection",
            "content": "Today I worked on my project and made progress.",
        },
    ]

    result = meta_reflection.analyze_reflections(repetitive_events)

    repetition_metrics = result["repetition_metrics"]
    assert repetition_metrics["repetition_ratio"] > 0.5  # Should detect high repetition
    assert (
        repetition_metrics["diversity_score"] < 0.3
    )  # Should show low diversity (adjusted for repetition penalty)


def test_detect_meta_anomalies_empty():
    """Test anomaly detection with empty summary."""
    meta_reflection = MetaReflection()

    empty_summary = {}
    anomalies = meta_reflection.detect_meta_anomalies(empty_summary)
    assert isinstance(anomalies, list)
    assert len(anomalies) == 0


def test_detect_meta_anomalies_bias():
    """Test detection of excessive stance bias."""
    meta_reflection = MetaReflection(bias_threshold=0.6)

    biased_summary = {
        "reflection_count": 5,
        "bias_metrics": {"stance_skew": 0.8},
        "depth_metrics": {"shallow_ratio": 0.3, "depth_score": 0.5},
        "closure_metrics": {"follow_through_ratio": 0.5, "commitment_mentions": 2},
        "repetition_metrics": {"repetition_ratio": 0.4, "diversity_score": 0.6},
    }

    anomalies = meta_reflection.detect_meta_anomalies(biased_summary)

    bias_flags = [a for a in anomalies if "excessive_stance_bias" in a]
    assert len(bias_flags) == 1
    assert "excessive_stance_bias:0.800" in bias_flags[0]


def test_detect_meta_anomalies_shallow():
    """Test detection of shallow reflection patterns."""
    meta_reflection = MetaReflection(shallow_threshold=0.5)

    shallow_summary = {
        "reflection_count": 5,
        "bias_metrics": {"stance_skew": 0.3},
        "depth_metrics": {"shallow_ratio": 0.7, "depth_score": 0.2},
        "closure_metrics": {"follow_through_ratio": 0.5, "commitment_mentions": 2},
        "repetition_metrics": {"repetition_ratio": 0.4, "diversity_score": 0.6},
    }

    anomalies = meta_reflection.detect_meta_anomalies(shallow_summary)

    shallow_flags = [a for a in anomalies if "shallow_reflection_pattern" in a]
    depth_flags = [a for a in anomalies if "low_depth_score" in a]
    assert len(shallow_flags) == 1
    assert len(depth_flags) == 1


def test_detect_meta_anomalies_closure():
    """Test detection of poor commitment closure."""
    meta_reflection = MetaReflection()

    poor_closure_summary = {
        "reflection_count": 5,
        "bias_metrics": {"stance_skew": 0.3},
        "depth_metrics": {"shallow_ratio": 0.3, "depth_score": 0.5},
        "closure_metrics": {"follow_through_ratio": 0.2, "commitment_mentions": 5},
        "repetition_metrics": {"repetition_ratio": 0.4, "diversity_score": 0.6},
    }

    anomalies = meta_reflection.detect_meta_anomalies(poor_closure_summary)

    closure_flags = [a for a in anomalies if "poor_commitment_closure" in a]
    assert len(closure_flags) == 1


def test_detect_meta_anomalies_repetition():
    """Test detection of excessive repetition and low diversity."""
    meta_reflection = MetaReflection()

    repetitive_summary = {
        "reflection_count": 10,
        "bias_metrics": {"stance_skew": 0.3},
        "depth_metrics": {"shallow_ratio": 0.3, "depth_score": 0.5},
        "closure_metrics": {
            "follow_through_ratio": 0.5,
            "commitment_mentions": 2,
            "evolution_indicators": 0,
        },
        "repetition_metrics": {"repetition_ratio": 0.9, "diversity_score": 0.1},
    }

    anomalies = meta_reflection.detect_meta_anomalies(repetitive_summary)

    repetition_flags = [a for a in anomalies if "excessive_repetition" in a]
    diversity_flags = [a for a in anomalies if "low_diversity" in a]
    stagnation_flags = [a for a in anomalies if "reflection_stagnation" in a]

    assert len(repetition_flags) == 1
    assert len(diversity_flags) == 1
    assert len(stagnation_flags) == 1


def test_maybe_emit_report_new():
    """Test emitting new meta-reflection report event."""
    meta_reflection = MetaReflection()
    eventlog = MockEventLog()

    summary = {
        "reflection_count": 3,
        "bias_metrics": {"stance_skew": 0.4},
        "depth_metrics": {"depth_score": 0.6},
        "closure_metrics": {"follow_through_ratio": 0.7},
        "repetition_metrics": {"diversity_score": 0.8},
    }

    event_id = meta_reflection.maybe_emit_report(eventlog, summary, "window_1")

    assert event_id is not None
    assert len(eventlog.events) == 1

    event = eventlog.events[0]
    assert event["kind"] == "meta_reflection_report"
    assert event["content"] == "meta_analysis"
    assert event["meta"]["component"] == "meta_reflection"
    assert event["meta"]["window"] == "window_1"
    assert event["meta"]["deterministic"] is True
    assert "digest" in event["meta"]


def test_maybe_emit_report_idempotent():
    """Test idempotent event emission (duplicate prevention)."""
    meta_reflection = MetaReflection()
    eventlog = MockEventLog()

    summary = {
        "reflection_count": 2,
        "bias_metrics": {"stance_skew": 0.3},
        "depth_metrics": {"depth_score": 0.5},
        "closure_metrics": {"follow_through_ratio": 0.6},
        "repetition_metrics": {"diversity_score": 0.7},
    }

    # First emission
    event_id1 = meta_reflection.maybe_emit_report(eventlog, summary, "window_test")
    assert event_id1 is not None
    assert len(eventlog.events) == 1

    # Second emission with same data - should be skipped
    event_id2 = meta_reflection.maybe_emit_report(eventlog, summary, "window_test")
    assert event_id2 is None
    assert len(eventlog.events) == 1  # No new event


def test_maybe_emit_report_different_data():
    """Test that different summary data produces new events."""
    meta_reflection = MetaReflection()
    eventlog = MockEventLog()

    summary1 = {
        "reflection_count": 2,
        "bias_metrics": {"stance_skew": 0.3},
        "depth_metrics": {"depth_score": 0.5},
        "closure_metrics": {"follow_through_ratio": 0.6},
        "repetition_metrics": {"diversity_score": 0.7},
    }
    summary2 = {
        "reflection_count": 3,  # Different count
        "bias_metrics": {"stance_skew": 0.3},
        "depth_metrics": {"depth_score": 0.5},
        "closure_metrics": {"follow_through_ratio": 0.6},
        "repetition_metrics": {"diversity_score": 0.7},
    }

    # First emission
    event_id1 = meta_reflection.maybe_emit_report(eventlog, summary1, "window_1")
    assert event_id1 is not None

    # Second emission with different data - should create new event
    event_id2 = meta_reflection.maybe_emit_report(eventlog, summary2, "window_1")
    assert event_id2 is not None
    assert len(eventlog.events) == 2


def test_deterministic_behavior():
    """Test that analysis is deterministic across multiple runs."""
    meta_reflection = MetaReflection()

    events = [
        {
            "id": "r1",
            "kind": "reflection",
            "content": "Great progress today with excellent results.",
        },
        {
            "id": "r2",
            "kind": "reflection",
            "content": "Terrible day with many failures and frustrations.",
        },
        {
            "id": "r3",
            "kind": "reflection",
            "content": "Average day with normal activities and okay outcomes.",
        },
    ]

    # Run analysis multiple times
    results = []
    for _ in range(3):
        summary = meta_reflection.analyze_reflections(events)
        results.append(summary)

    # All results should be identical
    for i in range(1, len(results)):
        assert results[i] == results[0]


def test_deterministic_digest():
    """Test that digest generation is deterministic."""
    meta_reflection = MetaReflection()

    summary = {
        "reflection_count": 2,
        "bias_metrics": {"stance_skew": 0.4, "positive_ratio": 0.6},
        "depth_metrics": {"depth_score": 0.5},
        "closure_metrics": {"follow_through_ratio": 0.7},
        "repetition_metrics": {"diversity_score": 0.8},
    }
    anomalies = ["excessive_stance_bias:0.400"]

    # Generate digest multiple times
    digests = []
    for _ in range(3):
        digest_data = meta_reflection._serialize_for_digest(
            summary, anomalies, "test_window"
        )
        digests.append(digest_data)

    # All digests should be identical
    for digest in digests[1:]:
        assert digest == digests[0]


def test_text_normalization():
    """Test text normalization consistency."""
    meta_reflection = MetaReflection()

    # Various text formats
    texts = [
        "Hello, World! This is a TEST.",
        "hello world this is a test",
        "Hello   World!!!   This    is a    TEST???",
        "HELLO, WORLD! THIS IS A TEST.",
    ]

    normalized = [meta_reflection._normalize_text(text) for text in texts]

    # All should normalize to the same result
    expected = "hello world this is a test"
    for norm in normalized:
        assert norm == expected


def test_bias_analysis_edge_cases():
    """Test bias analysis with edge cases."""
    meta_reflection = MetaReflection()

    # No stance keywords
    neutral_texts = ["Today I went to the store and bought groceries."]
    bias_metrics = meta_reflection._analyze_bias_patterns(neutral_texts)
    assert bias_metrics["stance_skew"] == 0.0

    # Empty texts
    empty_texts = ["", "   ", "\n\t"]
    bias_metrics = meta_reflection._analyze_bias_patterns(empty_texts)
    assert bias_metrics["stance_skew"] == 0.0


def test_depth_analysis_edge_cases():
    """Test depth analysis with edge cases."""
    meta_reflection = MetaReflection()

    # Very short texts
    short_texts = ["Hi.", "Ok.", "Yes."]
    depth_metrics = meta_reflection._analyze_depth_patterns(short_texts)
    assert depth_metrics["avg_token_length"] < 5.0

    # Empty texts
    empty_texts = []
    depth_metrics = meta_reflection._analyze_depth_patterns(empty_texts)
    assert depth_metrics["avg_token_length"] == 0.0


def test_repetition_analysis_edge_cases():
    """Test repetition analysis with edge cases."""
    meta_reflection = MetaReflection()

    # Single reflection
    single_text = ["This is a unique reflection with no repetition."]
    repetition_metrics = meta_reflection._analyze_repetition_patterns(single_text)
    assert (
        repetition_metrics["diversity_score"] == 0.0
    )  # Single text has no diversity by definition

    # Identical reflections
    identical_texts = ["Same text"] * 5
    repetition_metrics = meta_reflection._analyze_repetition_patterns(identical_texts)
    assert repetition_metrics["repetition_ratio"] > 0.8


def test_integration_workflow():
    """Test complete integration workflow: analyze -> detect -> emit."""
    meta_reflection = MetaReflection()
    eventlog = MockEventLog()

    # Simulate reflection events with various patterns
    events = [
        {
            "id": "r1",
            "kind": "reflection",
            "content": "Excellent day with great achievements and wonderful progress.",
        },
        {
            "id": "r2",
            "kind": "reflection",
            "content": "Another fantastic day with amazing results and successful outcomes.",
        },
        {
            "id": "r3",
            "kind": "reflection",
            "content": "Outstanding performance today with excellent work and proud accomplishments.",
        },
        {"id": "c1", "kind": "commitment_open", "content": "I will work harder"},
        {
            "id": "r4",
            "kind": "reflection",
            "content": "Reflecting on my commitment to work harder. I completed my goals and accomplished what I planned.",
        },
    ]

    # Step 1: Analyze reflections
    summary = meta_reflection.analyze_reflections(events)
    assert summary["reflection_count"] == 4

    # Step 2: Detect anomalies
    anomalies = meta_reflection.detect_meta_anomalies(summary)
    assert len(anomalies) > 0  # Should detect positive bias

    # Step 3: Emit report
    event_id = meta_reflection.maybe_emit_report(eventlog, summary, "integration_test")
    assert event_id is not None

    # Verify event structure
    event = eventlog.events[0]
    assert event["kind"] == "meta_reflection_report"
    assert event["meta"]["summary"] == summary
    assert event["meta"]["anomalies"] == anomalies
    assert event["meta"]["window"] == "integration_test"


def test_metadata_preservation():
    """Test that all metadata is properly preserved in events."""
    meta_reflection = MetaReflection(bias_threshold=0.8, shallow_threshold=0.7)
    eventlog = MockEventLog()

    summary = {
        "reflection_count": 5,
        "bias_metrics": {"stance_skew": 0.4},
        "depth_metrics": {"depth_score": 0.6},
        "closure_metrics": {"follow_through_ratio": 0.7},
        "repetition_metrics": {"diversity_score": 0.8},
    }

    meta_reflection.maybe_emit_report(eventlog, summary, "metadata_test")

    event = eventlog.events[0]
    meta = event["meta"]

    # Check all required metadata fields
    assert meta["component"] == "meta_reflection"
    assert meta["window"] == "metadata_test"
    assert meta["deterministic"] is True
    assert meta["bias_threshold"] == 0.8
    assert meta["shallow_threshold"] == 0.7
    assert meta["reflection_count"] == 5
    assert "digest" in meta
    assert "anomalies" in meta
    assert "summary" in meta


def test_custom_thresholds():
    """Test custom threshold configuration."""
    meta_reflection = MetaReflection(bias_threshold=0.9, shallow_threshold=0.8)

    # Test that thresholds are properly set and clamped
    assert meta_reflection.bias_threshold == 0.9
    assert meta_reflection.shallow_threshold == 0.8

    # Test threshold clamping
    meta_reflection_clamped = MetaReflection(bias_threshold=1.5, shallow_threshold=-0.5)
    assert meta_reflection_clamped.bias_threshold == 1.0  # Clamped to max
    assert meta_reflection_clamped.shallow_threshold == 0.0  # Clamped to min


def test_replayability():
    """Test that ledger replay yields identical meta-reflection reports."""
    meta_reflection = MetaReflection()

    # Same input events
    events = [
        {
            "id": "r1",
            "kind": "reflection",
            "content": "Great day with excellent progress and wonderful achievements.",
        },
        {
            "id": "r2",
            "kind": "reflection",
            "content": "Terrible day with many failures and frustrating setbacks.",
        },
    ]

    # Generate multiple reports with same data
    eventlogs = [MockEventLog() for _ in range(3)]
    event_ids = []

    for eventlog in eventlogs:
        summary = meta_reflection.analyze_reflections(events)
        event_id = meta_reflection.maybe_emit_report(eventlog, summary, "replay_test")
        event_ids.append(event_id)

    # All should produce events (first time)
    assert all(eid is not None for eid in event_ids)

    # All events should have identical metadata (except event IDs)
    events_emitted = [eventlog.events[0] for eventlog in eventlogs]
    for i in range(1, len(events_emitted)):
        assert (
            events_emitted[i]["meta"]["digest"] == events_emitted[0]["meta"]["digest"]
        )
        assert (
            events_emitted[i]["meta"]["summary"] == events_emitted[0]["meta"]["summary"]
        )
        assert (
            events_emitted[i]["meta"]["anomalies"]
            == events_emitted[0]["meta"]["anomalies"]
        )


def test_malformed_events():
    """Test handling of malformed events gracefully."""
    meta_reflection = MetaReflection()

    # Events with missing fields
    malformed_events = [
        {"kind": "reflection"},  # Missing content
        {"id": "r2", "content": "test"},  # Missing kind
        {"id": "r3", "kind": "reflection", "content": None},  # None content
        {"id": "r4", "kind": "reflection", "content": "Valid reflection content"},
    ]

    result = meta_reflection.analyze_reflections(malformed_events)

    # Should handle gracefully and process valid reflections
    assert result["reflection_count"] == 1  # Only one valid reflection


def test_empty_reflection_content():
    """Test handling of empty reflection content."""
    meta_reflection = MetaReflection()

    events = [
        {"id": "r1", "kind": "reflection", "content": ""},
        {"id": "r2", "kind": "reflection", "content": "   "},
        {"id": "r3", "kind": "reflection", "content": "\n\t"},
        {"id": "r4", "kind": "reflection", "content": "Valid content"},
    ]

    result = meta_reflection.analyze_reflections(events)

    # Should only count non-empty reflections
    assert result["reflection_count"] == 1
