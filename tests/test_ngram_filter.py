"""Tests for the NgramRepeatAnalyzer class.

Comprehensive test suite covering deterministic n-gram analysis, repeat detection,
idempotent event emission, and CONTRIBUTING.md compliance.
"""

from pmm.runtime.filters.ngram_filter import NgramRepeatAnalyzer


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


def test_analyze_reflection_text_empty():
    """Test analysis of empty/invalid text."""
    filter_obj = NgramRepeatAnalyzer()

    # Empty string
    result = filter_obj.analyze_reflection_text("")
    assert result["normalized_text"] == ""
    assert result["total_tokens"] == 0
    assert result["ngrams"] == {}
    assert result["ngram_counts"] == {}

    # None input
    result = filter_obj.analyze_reflection_text(None)
    assert result["normalized_text"] == ""
    assert result["total_tokens"] == 0


def test_analyze_reflection_text_basic():
    """Test basic n-gram analysis."""
    filter_obj = NgramRepeatAnalyzer()
    text = "I am learning to be better. I am growing."

    result = filter_obj.analyze_reflection_text(text)

    assert result["normalized_text"] == "i am learning to be better i am growing"
    assert result["total_tokens"] == 9
    assert "2gram" in result["ngrams"]
    assert "3gram" in result["ngrams"]

    # Check 2-grams
    expected_2grams = [
        "i am",
        "am learning",
        "learning to",
        "to be",
        "be better",
        "better i",
        "i am",
        "am growing",
    ]
    assert result["ngrams"]["2gram"] == expected_2grams

    # Check 2-gram counts
    assert result["ngram_counts"]["2gram"]["i am"] == 2
    assert result["ngram_counts"]["2gram"]["am learning"] == 1


def test_analyze_reflection_text_normalization():
    """Test text normalization (punctuation, case, whitespace)."""
    filter_obj = NgramRepeatAnalyzer()
    text = "Hello, World!   This is... A TEST!!!"

    result = filter_obj.analyze_reflection_text(text)

    assert result["normalized_text"] == "hello world this is a test"
    assert result["total_tokens"] == 6


def test_detect_repeats_none():
    """Test repeat detection with no repeats."""
    filter_obj = NgramRepeatAnalyzer(repeat_threshold=3)

    analysis = {
        "ngram_counts": {
            "2gram": {"hello world": 1, "world this": 1},
            "3gram": {"hello world this": 1},
        }
    }

    repeats = filter_obj.detect_repeats(analysis)
    assert repeats == []


def test_detect_repeats_found():
    """Test repeat detection with actual repeats."""
    filter_obj = NgramRepeatAnalyzer(repeat_threshold=3)

    analysis = {
        "ngram_counts": {
            "2gram": {"i am": 4, "am learning": 1},
            "3gram": {"i am learning": 3},
        }
    }

    repeats = filter_obj.detect_repeats(analysis)
    assert len(repeats) == 2
    assert "2gram_repeat:4:i am" in repeats
    assert "3gram_repeat:3:i am learning" in repeats


def test_detect_repeats_empty_analysis():
    """Test repeat detection with empty analysis."""
    filter_obj = NgramRepeatAnalyzer()

    repeats = filter_obj.detect_repeats({})
    assert repeats == []

    repeats = filter_obj.detect_repeats({"ngram_counts": {}})
    assert repeats == []


def test_maybe_emit_filter_event_new():
    """Test emitting new filter event."""
    filter_obj = NgramRepeatAnalyzer()
    eventlog = MockEventLog()

    analysis = {
        "normalized_text": "hello world",
        "total_tokens": 2,
        "ngram_counts": {"2gram": {"hello world": 1}},
    }
    repeats = []

    event_id = filter_obj.maybe_emit_filter_event(
        eventlog, "src_123", analysis, repeats
    )

    assert event_id is not None
    assert len(eventlog.events) == 1

    event = eventlog.events[0]
    assert event["kind"] == "ngram_filter_report"
    assert event["content"] == "analysis"
    assert event["meta"]["component"] == "ngram_filter"
    assert event["meta"]["src_event_id"] == "src_123"
    assert event["meta"]["deterministic"] is True
    assert "digest" in event["meta"]


def test_maybe_emit_filter_event_idempotent():
    """Test idempotent event emission (duplicate prevention)."""
    filter_obj = NgramRepeatAnalyzer()
    eventlog = MockEventLog()

    analysis = {
        "normalized_text": "hello world",
        "total_tokens": 2,
        "ngram_counts": {"2gram": {"hello world": 1}},
    }
    repeats = []

    # First emission
    event_id1 = filter_obj.maybe_emit_filter_event(
        eventlog, "src_123", analysis, repeats
    )
    assert event_id1 is not None
    assert len(eventlog.events) == 1

    # Second emission with same data - should be skipped
    event_id2 = filter_obj.maybe_emit_filter_event(
        eventlog, "src_123", analysis, repeats
    )
    assert event_id2 is None
    assert len(eventlog.events) == 1  # No new event


def test_maybe_emit_filter_event_different_data():
    """Test that different analysis data produces new events."""
    filter_obj = NgramRepeatAnalyzer()
    eventlog = MockEventLog()

    analysis1 = {
        "normalized_text": "hello world",
        "total_tokens": 2,
        "ngram_counts": {"2gram": {"hello world": 1}},
    }
    analysis2 = {
        "normalized_text": "goodbye world",
        "total_tokens": 2,
        "ngram_counts": {"2gram": {"goodbye world": 1}},
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
    filter_obj = NgramRepeatAnalyzer()
    text = "I am learning to be better. I am growing every day."

    # Run analysis multiple times
    results = []
    for _ in range(3):
        result = filter_obj.analyze_reflection_text(text)
        results.append(result)

    # All results should be identical
    for i in range(1, len(results)):
        assert results[i] == results[0]


def test_deterministic_digest():
    """Test that digest generation is deterministic."""
    filter_obj = NgramRepeatAnalyzer()

    analysis = {
        "normalized_text": "hello world",
        "total_tokens": 2,
        "ngram_counts": {"2gram": {"hello world": 1}},
    }
    repeats = ["2gram_repeat:3:hello world"]

    # Generate digest multiple times
    digests = []
    for _ in range(3):
        digest_data = filter_obj._serialize_for_digest(analysis, repeats)
        digests.append(digest_data)

    # All digests should be identical
    for digest in digests[1:]:
        assert digest == digests[0]


def test_custom_ngram_lengths():
    """Test custom n-gram lengths configuration."""
    filter_obj = NgramRepeatAnalyzer(ngram_lengths=[2, 4])
    text = "one two three four five six"

    result = filter_obj.analyze_reflection_text(text)

    assert "2gram" in result["ngrams"]
    assert "4gram" in result["ngrams"]
    assert "3gram" not in result["ngrams"]

    # Check 4-grams
    expected_4grams = [
        "one two three four",
        "two three four five",
        "three four five six",
    ]
    assert result["ngrams"]["4gram"] == expected_4grams


def test_custom_repeat_threshold():
    """Test custom repeat threshold configuration."""
    filter_obj = NgramRepeatAnalyzer(repeat_threshold=2)

    analysis = {"ngram_counts": {"2gram": {"hello world": 2, "world hello": 1}}}

    repeats = filter_obj.detect_repeats(analysis)
    assert len(repeats) == 1
    assert "2gram_repeat:2:hello world" in repeats


def test_integration_workflow():
    """Test complete integration workflow: analyze -> detect -> emit."""
    filter_obj = NgramRepeatAnalyzer(repeat_threshold=2)
    eventlog = MockEventLog()

    # Text with repetitive patterns
    text = "I am learning. I am growing. I am learning to be better."

    # Step 1: Analyze
    analysis = filter_obj.analyze_reflection_text(text)
    assert analysis["total_tokens"] == 12

    # Step 2: Detect repeats
    repeats = filter_obj.detect_repeats(analysis)
    assert len(repeats) > 0  # Should find "i am" repeated

    # Step 3: Emit event
    event_id = filter_obj.maybe_emit_filter_event(
        eventlog, "src_reflection_123", analysis, repeats
    )
    assert event_id is not None

    # Verify event structure
    event = eventlog.events[0]
    assert event["kind"] == "ngram_filter_report"
    assert event["meta"]["analysis"] == analysis
    assert event["meta"]["repeats"] == repeats
    assert event["meta"]["src_event_id"] == "src_reflection_123"


def test_metadata_preservation():
    """Test that all metadata is properly preserved in events."""
    filter_obj = NgramRepeatAnalyzer(repeat_threshold=5, ngram_lengths=[2, 3, 4])
    eventlog = MockEventLog()

    analysis = {
        "normalized_text": "test text",
        "total_tokens": 2,
        "ngram_counts": {"2gram": {"test text": 1}},
    }
    repeats = []

    filter_obj.maybe_emit_filter_event(eventlog, "src_456", analysis, repeats)

    event = eventlog.events[0]
    meta = event["meta"]

    # Check all required metadata fields
    assert meta["component"] == "ngram_filter"
    assert meta["src_event_id"] == "src_456"
    assert meta["deterministic"] is True
    assert meta["threshold_used"] == 5
    assert meta["ngram_lengths"] == [2, 3, 4]
    assert meta["total_tokens"] == 2
    assert "digest" in meta
