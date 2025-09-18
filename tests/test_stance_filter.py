"""Tests for StanceFilter class.

Comprehensive test suite covering deterministic stance analysis, shift detection,
idempotent event emission, and CONTRIBUTING.md compliance.
"""

from pmm.runtime.filters.stance_filter import StanceFilter


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


def test_analyze_commitment_text_empty():
    """Test analysis of empty/invalid text."""
    filter_obj = StanceFilter()

    # Empty string
    result = filter_obj.analyze_commitment_text("")
    assert result["normalized_text"] == ""
    assert result["detected_stances"] == {}
    assert result["stance_summary"] == {}

    # None input
    result = filter_obj.analyze_commitment_text(None)
    assert result["normalized_text"] == ""
    assert result["detected_stances"] == {}


def test_analyze_commitment_text_basic():
    """Test basic stance detection."""
    filter_obj = StanceFilter()
    text = "I must complete this task and I will ensure success."

    result = filter_obj.analyze_commitment_text(text)

    assert (
        result["normalized_text"]
        == "i must complete this task and i will ensure success."
    )
    assert "obligation" in result["detected_stances"]
    assert "commitment" in result["detected_stances"]

    # Check obligation detection
    assert "strong" in result["detected_stances"]["obligation"]
    assert "must" in result["detected_stances"]["obligation"]["strong"]

    # Check commitment detection
    assert "strong" in result["detected_stances"]["commitment"]
    assert "will" in result["detected_stances"]["commitment"]["strong"]
    assert "ensure" in result["detected_stances"]["commitment"]["strong"]

    # Check stance summary
    assert result["stance_summary"]["obligation_strong"] == 1
    assert result["stance_summary"]["commitment_strong"] == 2


def test_analyze_commitment_text_multiple_intensities():
    """Test detection of multiple stance intensities."""
    filter_obj = StanceFilter()
    text = "I must do this, I should try that, and I might consider the other."

    result = filter_obj.analyze_commitment_text(text)

    # Check all intensities detected
    assert result["stance_summary"]["obligation_strong"] == 1  # must
    assert result["stance_summary"]["obligation_moderate"] == 1  # should
    assert result["stance_summary"]["obligation_weak"] == 1  # might


def test_analyze_commitment_text_word_boundaries():
    """Test that word boundary matching works correctly."""
    filter_obj = StanceFilter()
    text = "I cannot do this, but I can help with something else."

    result = filter_obj.analyze_commitment_text(text)

    # "cannot" should be detected as prohibition, "can" as capability
    assert result["stance_summary"]["prohibition_strong"] == 1  # cannot
    assert result["stance_summary"]["capability_strong"] == 1  # can


def test_detect_shifts_empty():
    """Test shift detection with empty/insufficient history."""
    filter_obj = StanceFilter()

    # Empty history
    shifts = filter_obj.detect_shifts([])
    assert shifts == []

    # Single commitment
    analysis = {"stance_summary": {"obligation_strong": 1}}
    shifts = filter_obj.detect_shifts([analysis])
    assert shifts == []


def test_detect_shifts_no_contradictions():
    """Test shift detection with consistent stances."""
    filter_obj = StanceFilter()

    history = [
        {"stance_summary": {"commitment_strong": 1}},
        {"stance_summary": {"commitment_strong": 2}},
        {"stance_summary": {"commitment_moderate": 1}},
    ]

    shifts = filter_obj.detect_shifts(history)
    assert shifts == []


def test_detect_shifts_contradictory():
    """Test detection of contradictory stance shifts."""
    filter_obj = StanceFilter()

    history = [
        {"stance_summary": {"obligation_strong": 1}},  # "must"
        {"stance_summary": {"prohibition_strong": 1}},  # "never"
    ]

    shifts = filter_obj.detect_shifts(history)
    assert len(shifts) == 1
    assert "stance_shift:obligation_strong->prohibition_strong" in shifts[0]


def test_detect_shifts_intensity_contradictions():
    """Test detection of same-category intensity contradictions."""
    filter_obj = StanceFilter()

    history = [
        {"stance_summary": {"commitment_strong": 1}},  # "will"
        {"stance_summary": {"commitment_weak": 1}},  # "hope"
    ]

    shifts = filter_obj.detect_shifts(history)
    assert len(shifts) == 1
    assert "stance_shift:commitment_strong->commitment_weak" in shifts[0]


def test_detect_shifts_window_limit():
    """Test that shift detection respects window size."""
    filter_obj = StanceFilter(shift_window=2)

    # History longer than window
    history = [
        {"stance_summary": {"obligation_strong": 1}},
        {"stance_summary": {"commitment_moderate": 1}},
        {"stance_summary": {"prohibition_strong": 1}},
        {"stance_summary": {"capability_strong": 1}},
    ]

    shifts = filter_obj.detect_shifts(history)

    # Should only analyze last 2 commitments (prohibition -> capability)
    # prohibition_strong -> capability_strong is contradictory, so expect shifts
    assert len(shifts) > 0


def test_maybe_emit_filter_event_new():
    """Test emitting new stance filter event."""
    filter_obj = StanceFilter()
    eventlog = MockEventLog()

    analysis = {
        "normalized_text": "i must do this",
        "detected_stances": {"obligation": {"strong": ["must"]}},
        "stance_summary": {"obligation_strong": 1},
    }
    shifts = []

    event_id = filter_obj.maybe_emit_filter_event(eventlog, "src_123", analysis, shifts)

    assert event_id is not None
    assert len(eventlog.events) == 1

    event = eventlog.events[0]
    assert event["kind"] == "stance_filter_report"
    assert event["content"] == "analysis"
    assert event["meta"]["component"] == "stance_filter"
    assert event["meta"]["src_event_id"] == "src_123"
    assert event["meta"]["deterministic"] is True
    assert "digest" in event["meta"]


def test_maybe_emit_filter_event_idempotent():
    """Test idempotent event emission (duplicate prevention)."""
    filter_obj = StanceFilter()
    eventlog = MockEventLog()

    analysis = {
        "normalized_text": "i must do this",
        "detected_stances": {"obligation": {"strong": ["must"]}},
        "stance_summary": {"obligation_strong": 1},
    }
    shifts = []

    # First emission
    event_id1 = filter_obj.maybe_emit_filter_event(
        eventlog, "src_123", analysis, shifts
    )
    assert event_id1 is not None
    assert len(eventlog.events) == 1

    # Second emission with same data - should be skipped
    event_id2 = filter_obj.maybe_emit_filter_event(
        eventlog, "src_123", analysis, shifts
    )
    assert event_id2 is None
    assert len(eventlog.events) == 1  # No new event


def test_maybe_emit_filter_event_different_data():
    """Test that different analysis data produces new events."""
    filter_obj = StanceFilter()
    eventlog = MockEventLog()

    analysis1 = {
        "normalized_text": "i must do this",
        "detected_stances": {"obligation": {"strong": ["must"]}},
        "stance_summary": {"obligation_strong": 1},
    }
    analysis2 = {
        "normalized_text": "i will do this",
        "detected_stances": {"commitment": {"strong": ["will"]}},
        "stance_summary": {"commitment_strong": 1},
    }

    # First emission
    event_id1 = filter_obj.maybe_emit_filter_event(eventlog, "src_123", analysis1, [])
    assert event_id1 is not None

    # Second emission with different data - should create new event
    event_id2 = filter_obj.maybe_emit_filter_event(eventlog, "src_124", analysis2, [])
    assert event_id2 is not None
    assert len(eventlog.events) == 2


def test_deterministic_behavior():
    """Test that analysis is deterministic across multiple runs."""
    filter_obj = StanceFilter()
    text = "I must complete this task and I will ensure success."

    # Run analysis multiple times
    results = []
    for _ in range(3):
        result = filter_obj.analyze_commitment_text(text)
        results.append(result)

    # All results should be identical
    for i in range(1, len(results)):
        assert results[i] == results[0]


def test_deterministic_digest():
    """Test that digest generation is deterministic."""
    filter_obj = StanceFilter()

    analysis = {
        "normalized_text": "i must do this",
        "detected_stances": {"obligation": {"strong": ["must"]}},
        "stance_summary": {"obligation_strong": 1},
    }
    shifts = ["stance_shift:obligation_strong->prohibition_strong:positions_0_1"]

    # Generate digest multiple times
    digests = []
    for _ in range(3):
        digest_data = filter_obj._serialize_for_digest(analysis, shifts)
        digests.append(digest_data)

    # All digests should be identical
    for digest in digests[1:]:
        assert digest == digests[0]


def test_stance_categories_coverage():
    """Test that all stance categories are properly detected."""
    filter_obj = StanceFilter()

    # Test each category
    test_cases = [
        ("I must do this", "obligation", "strong"),
        ("I should try this", "obligation", "moderate"),
        ("I might consider this", "obligation", "weak"),
        ("I never do that", "prohibition", "strong"),
        ("I should not do that", "prohibition", "moderate"),
        ("I prefer not to do that", "prohibition", "weak"),
        ("I will complete this", "commitment", "strong"),
        ("I intend to finish this", "commitment", "moderate"),
        ("I hope to try this", "commitment", "weak"),
        ("I can handle this", "capability", "strong"),
        ("I am competent at this", "capability", "moderate"),
        ("I am learning this", "capability", "weak"),
    ]

    for text, expected_category, expected_intensity in test_cases:
        result = filter_obj.analyze_commitment_text(text)
        assert expected_category in result["detected_stances"]
        assert expected_intensity in result["detected_stances"][expected_category]
        assert f"{expected_category}_{expected_intensity}" in result["stance_summary"]


def test_custom_shift_window():
    """Test custom shift window configuration."""
    filter_obj = StanceFilter(shift_window=3)

    # Create history longer than window
    history = [
        {"stance_summary": {"obligation_strong": 1}},
        {"stance_summary": {"commitment_moderate": 1}},
        {"stance_summary": {"prohibition_strong": 1}},
        {"stance_summary": {"capability_strong": 1}},
        {"stance_summary": {"commitment_strong": 1}},
    ]

    shifts = filter_obj.detect_shifts(history)

    # Should only analyze last 3 commitments
    # Check that window size is respected in metadata
    eventlog = MockEventLog()
    analysis = {"stance_summary": {}}
    filter_obj.maybe_emit_filter_event(eventlog, "src_123", analysis, shifts)

    event = eventlog.events[0]
    assert event["meta"]["shift_window"] == 3


def test_integration_workflow():
    """Test complete integration workflow: analyze -> detect -> emit."""
    filter_obj = StanceFilter(shift_window=3)
    eventlog = MockEventLog()

    # Simulate commitment sequence with contradictory stances
    commitment_texts = [
        "I must complete this project",
        "I will ensure it gets done",
        "I never want to work on this again",
    ]

    # Analyze each commitment
    analyses = []
    for text in commitment_texts:
        analysis = filter_obj.analyze_commitment_text(text)
        analyses.append(analysis)

    # Detect shifts across the sequence
    shifts = filter_obj.detect_shifts(analyses)
    assert len(shifts) > 0  # Should detect contradictions

    # Emit event for the final analysis
    event_id = filter_obj.maybe_emit_filter_event(
        eventlog, "src_commitment_456", analyses[-1], shifts
    )
    assert event_id is not None

    # Verify event structure
    event = eventlog.events[0]
    assert event["kind"] == "stance_filter_report"
    assert event["meta"]["analysis"] == analyses[-1]
    assert event["meta"]["shifts"] == shifts
    assert event["meta"]["src_event_id"] == "src_commitment_456"


def test_metadata_preservation():
    """Test that all metadata is properly preserved in events."""
    filter_obj = StanceFilter(shift_window=7)
    eventlog = MockEventLog()

    analysis = {
        "normalized_text": "i must do this",
        "detected_stances": {"obligation": {"strong": ["must"]}},
        "stance_summary": {"obligation_strong": 1},
    }
    shifts = ["stance_shift:obligation_strong->prohibition_strong:positions_0_1"]

    filter_obj.maybe_emit_filter_event(eventlog, "src_789", analysis, shifts)

    event = eventlog.events[0]
    meta = event["meta"]

    # Check all required metadata fields
    assert meta["component"] == "stance_filter"
    assert meta["src_event_id"] == "src_789"
    assert meta["deterministic"] is True
    assert meta["shift_window"] == 7
    assert meta["categories_analyzed"] == list(filter_obj.STANCE_CATEGORIES.keys())
    assert meta["stance_count"] == 1
    assert "digest" in meta


def test_contradictory_pairs_detection():
    """Test specific contradictory pair detection logic."""
    filter_obj = StanceFilter()

    # Test known contradictory pairs
    contradictory_cases = [
        (("obligation", "strong"), ("prohibition", "strong")),
        (("obligation", "strong"), ("prohibition", "moderate")),
        (("commitment", "strong"), ("prohibition", "strong")),
        (("capability", "strong"), ("prohibition", "strong")),
    ]

    for stance1, stance2 in contradictory_cases:
        assert filter_obj._is_contradictory_pair(stance1, stance2)
        assert filter_obj._is_contradictory_pair(stance2, stance1)  # Symmetric

    # Test non-contradictory pairs
    non_contradictory_cases = [
        (("obligation", "strong"), ("commitment", "strong")),
        (("capability", "moderate"), ("commitment", "moderate")),
    ]

    for stance1, stance2 in non_contradictory_cases:
        assert not filter_obj._is_contradictory_pair(stance1, stance2)


def test_normalization_preserves_boundaries():
    """Test that text normalization preserves word boundaries for matching."""
    filter_obj = StanceFilter()

    # Text with punctuation that could affect word boundaries
    text = "I can't do this, but I cannot give up!"

    result = filter_obj.analyze_commitment_text(text)

    # Should detect "cannot" but not partial matches
    assert result["stance_summary"]["prohibition_strong"] == 1  # cannot
    # "can't" contains "can" and should be detected separately from "cannot"
    assert result["stance_summary"]["capability_strong"] == 1  # can
