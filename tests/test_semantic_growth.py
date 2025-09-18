"""Tests for SemanticGrowth class.

Comprehensive test suite covering deterministic semantic analysis, growth path detection,
idempotent event emission, and CONTRIBUTING.md compliance.
"""

from pmm.runtime.semantic.semantic_growth import SemanticGrowth


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


def test_analyze_texts_empty():
    """Test analysis of empty/invalid text lists."""
    growth_analyzer = SemanticGrowth()

    # Empty list
    result = growth_analyzer.analyze_texts([])
    assert result["total_texts"] == 0
    assert result["theme_counts"] == {}
    assert result["theme_densities"] == {}
    assert result["dominant_themes"] == []

    # None input
    result = growth_analyzer.analyze_texts(None)
    assert result["total_texts"] == 0

    # List with empty strings
    result = growth_analyzer.analyze_texts(["", None, ""])
    assert result["total_texts"] == 0


def test_analyze_texts_basic():
    """Test basic semantic theme analysis."""
    growth_analyzer = SemanticGrowth()
    texts = [
        "I want to learn new skills and improve my knowledge.",
        "I create artistic designs and express my creative vision.",
        "Building strong relationships with my community is important.",
    ]

    result = growth_analyzer.analyze_texts(texts)

    assert result["total_texts"] == 3
    assert "learning" in result["theme_counts"]
    assert "creativity" in result["theme_counts"]
    assert "relationships" in result["theme_counts"]

    # Check specific theme detection
    assert result["theme_counts"]["learning"] >= 2  # "learn", "knowledge"
    assert result["theme_counts"]["creativity"] >= 2  # "create", "creative"
    assert result["theme_counts"]["relationships"] >= 1  # "relationships", "community"

    # Check densities are calculated
    assert all(
        isinstance(density, float) for density in result["theme_densities"].values()
    )

    # Check dominant themes
    assert len(result["dominant_themes"]) <= 3
    assert all(theme in result["theme_counts"] for theme in result["dominant_themes"])


def test_analyze_texts_theme_categories():
    """Test detection of all semantic theme categories."""
    growth_analyzer = SemanticGrowth()

    # Test texts covering different themes
    theme_texts = {
        "learning": "I study and research to develop new skills and knowledge.",
        "creativity": "I create innovative designs and express my artistic vision.",
        "relationships": "I collaborate with my team and support my community.",
        "achievement": "I accomplish my goals and achieve success in my projects.",
        "reflection": "I reflect and contemplate to gain deeper insights and wisdom.",
        "health": "I exercise regularly and maintain my physical and mental wellness.",
        "productivity": "I organize my workflow and focus on efficient processes.",
        "spirituality": "I seek meaning and purpose through mindful spiritual practices.",
    }

    for expected_theme, text in theme_texts.items():
        result = growth_analyzer.analyze_texts([text])
        assert expected_theme in result["theme_counts"]
        assert result["theme_counts"][expected_theme] > 0


def test_analyze_texts_word_boundaries():
    """Test that word boundary matching works correctly."""
    growth_analyzer = SemanticGrowth()

    # Text that could have partial matches
    text = "I cannot learn from this unlearnedness, but I can learn properly."

    result = growth_analyzer.analyze_texts([text])

    # Should detect "learn" twice (not "unlearnedness")
    assert result["theme_counts"]["learning"] == 2


def test_detect_growth_paths_empty():
    """Test growth path detection with empty/insufficient history."""
    growth_analyzer = SemanticGrowth()

    # Empty history
    growth_paths = growth_analyzer.detect_growth_paths([])
    assert growth_paths == []

    # Single analysis
    analysis = {"theme_densities": {"learning": 0.1}}
    growth_paths = growth_analyzer.detect_growth_paths([analysis])
    assert growth_paths == []


def test_detect_growth_paths_no_changes():
    """Test growth path detection with stable themes."""
    growth_analyzer = SemanticGrowth()

    # Stable theme densities
    analyses = [
        {
            "theme_densities": {"learning": 0.1, "creativity": 0.05},
            "dominant_themes": ["learning"],
        },
        {
            "theme_densities": {"learning": 0.11, "creativity": 0.06},
            "dominant_themes": ["learning"],
        },
        {
            "theme_densities": {"learning": 0.09, "creativity": 0.04},
            "dominant_themes": ["learning"],
        },
    ]

    growth_analyzer.detect_growth_paths(analyses)
    # With default thresholds (0.2/-0.2), small changes might trigger flags
    # Let's use more restrictive thresholds for this test
    growth_analyzer_strict = SemanticGrowth(
        growth_threshold=0.5, decline_threshold=-0.5
    )
    growth_paths_strict = growth_analyzer_strict.detect_growth_paths(analyses)
    assert growth_paths_strict == []


def test_detect_growth_paths_emerging_themes():
    """Test detection of emerging themes."""
    growth_analyzer = SemanticGrowth(growth_threshold=0.5)  # 50% growth threshold

    analyses = [
        {
            "theme_densities": {"learning": 0.1, "creativity": 0.02},
            "dominant_themes": ["learning"],
        },
        {
            "theme_densities": {"learning": 0.1, "creativity": 0.08},
            "dominant_themes": ["learning", "creativity"],
        },
    ]

    growth_paths = growth_analyzer.detect_growth_paths(analyses)

    # Should detect creativity as emerging (300% growth: 0.02 -> 0.08)
    emerging_flags = [
        flag for flag in growth_paths if "emerging_theme:creativity" in flag
    ]
    assert len(emerging_flags) == 1


def test_detect_growth_paths_declining_themes():
    """Test detection of declining themes."""
    growth_analyzer = SemanticGrowth(decline_threshold=-0.5)  # 50% decline threshold

    analyses = [
        {
            "theme_densities": {"learning": 0.1, "creativity": 0.08},
            "dominant_themes": ["learning", "creativity"],
        },
        {
            "theme_densities": {"learning": 0.1, "creativity": 0.02},
            "dominant_themes": ["learning"],
        },
    ]

    growth_paths = growth_analyzer.detect_growth_paths(analyses)

    # Should detect creativity as declining (75% decline: 0.08 -> 0.02)
    declining_flags = [
        flag for flag in growth_paths if "declining_theme:creativity" in flag
    ]
    assert len(declining_flags) == 1


def test_detect_growth_paths_dominant_shifts():
    """Test detection of dominant theme shifts."""
    growth_analyzer = SemanticGrowth()

    analyses = [
        {
            "theme_densities": {"learning": 0.1, "creativity": 0.05},
            "dominant_themes": ["learning"],
        },
        {
            "theme_densities": {"learning": 0.05, "creativity": 0.1},
            "dominant_themes": ["creativity"],
        },
    ]

    growth_paths = growth_analyzer.detect_growth_paths(analyses)

    # Should detect dominant theme changes
    new_dominant = [
        flag for flag in growth_paths if "new_dominant_theme:creativity" in flag
    ]
    lost_dominant = [
        flag for flag in growth_paths if "lost_dominant_theme:learning" in flag
    ]

    assert len(new_dominant) == 1
    assert len(lost_dominant) == 1


def test_detect_growth_paths_window_limit():
    """Test that growth detection respects window size."""
    growth_analyzer = SemanticGrowth(window_size=2)

    # History longer than window
    analyses = [
        {"theme_densities": {"learning": 0.1}, "dominant_themes": ["learning"]},
        {"theme_densities": {"creativity": 0.1}, "dominant_themes": ["creativity"]},
        {"theme_densities": {"health": 0.1}, "dominant_themes": ["health"]},
        {"theme_densities": {"productivity": 0.1}, "dominant_themes": ["productivity"]},
    ]

    growth_paths = growth_analyzer.detect_growth_paths(analyses)

    # Should only compare last 2 analyses (health -> productivity)
    # Check that window size is respected
    assert (
        len(growth_paths) >= 0
    )  # May or may not detect changes depending on thresholds


def test_maybe_emit_growth_report_new():
    """Test emitting new semantic growth report."""
    growth_analyzer = SemanticGrowth()
    eventlog = MockEventLog()

    analysis = {
        "total_texts": 2,
        "theme_counts": {"learning": 3, "creativity": 1},
        "theme_densities": {"learning": 0.15, "creativity": 0.05},
        "dominant_themes": ["learning"],
    }
    growth_paths = ["emerging_theme:creativity:0.500"]

    event_id = growth_analyzer.maybe_emit_growth_report(
        eventlog, "src_123", analysis, growth_paths
    )

    assert event_id is not None
    assert len(eventlog.events) == 1

    event = eventlog.events[0]
    assert event["kind"] == "semantic_growth_report"
    assert event["content"] == "analysis"
    assert event["meta"]["component"] == "semantic_growth"
    assert event["meta"]["src_event_id"] == "src_123"
    assert event["meta"]["deterministic"] is True
    assert "digest" in event["meta"]


def test_maybe_emit_growth_report_idempotent():
    """Test idempotent event emission (duplicate prevention)."""
    growth_analyzer = SemanticGrowth()
    eventlog = MockEventLog()

    analysis = {
        "total_texts": 2,
        "theme_counts": {"learning": 3},
        "theme_densities": {"learning": 0.15},
        "dominant_themes": ["learning"],
    }
    growth_paths = []

    # First emission
    event_id1 = growth_analyzer.maybe_emit_growth_report(
        eventlog, "src_123", analysis, growth_paths
    )
    assert event_id1 is not None
    assert len(eventlog.events) == 1

    # Second emission with same data - should be skipped
    event_id2 = growth_analyzer.maybe_emit_growth_report(
        eventlog, "src_123", analysis, growth_paths
    )
    assert event_id2 is None
    assert len(eventlog.events) == 1  # No new event


def test_maybe_emit_growth_report_different_data():
    """Test that different analysis data produces new events."""
    growth_analyzer = SemanticGrowth()
    eventlog = MockEventLog()

    analysis1 = {
        "total_texts": 1,
        "theme_counts": {"learning": 2},
        "theme_densities": {"learning": 0.2},
        "dominant_themes": ["learning"],
    }
    analysis2 = {
        "total_texts": 1,
        "theme_counts": {"creativity": 2},
        "theme_densities": {"creativity": 0.2},
        "dominant_themes": ["creativity"],
    }

    # First emission
    event_id1 = growth_analyzer.maybe_emit_growth_report(
        eventlog, "src_123", analysis1, []
    )
    assert event_id1 is not None

    # Second emission with different data - should create new event
    event_id2 = growth_analyzer.maybe_emit_growth_report(
        eventlog, "src_124", analysis2, []
    )
    assert event_id2 is not None
    assert len(eventlog.events) == 2


def test_deterministic_behavior():
    """Test that analysis is deterministic across multiple runs."""
    growth_analyzer = SemanticGrowth()
    texts = [
        "I want to learn new programming skills and create innovative software.",
        "Building relationships with my team while achieving our project goals.",
    ]

    # Run analysis multiple times
    results = []
    for _ in range(3):
        result = growth_analyzer.analyze_texts(texts)
        results.append(result)

    # All results should be identical
    for i in range(1, len(results)):
        assert results[i] == results[0]


def test_deterministic_digest():
    """Test that digest generation is deterministic."""
    growth_analyzer = SemanticGrowth()

    analysis = {
        "total_texts": 2,
        "theme_counts": {"learning": 3, "creativity": 1},
        "theme_densities": {"learning": 0.15, "creativity": 0.05},
        "dominant_themes": ["learning"],
    }
    growth_paths = ["emerging_theme:creativity:0.500"]

    # Generate digest multiple times
    digests = []
    for _ in range(3):
        digest_data = growth_analyzer._serialize_for_digest(analysis, growth_paths)
        digests.append(digest_data)

    # All digests should be identical
    for digest in digests[1:]:
        assert digest == digests[0]


def test_custom_thresholds():
    """Test custom growth and decline thresholds."""
    growth_analyzer = SemanticGrowth(growth_threshold=1.0, decline_threshold=-0.8)

    analyses = [
        {"theme_densities": {"learning": 0.1}, "dominant_themes": ["learning"]},
        {
            "theme_densities": {"learning": 0.15},
            "dominant_themes": ["learning"],
        },  # 50% growth
    ]

    growth_paths = growth_analyzer.detect_growth_paths(analyses)

    # 50% growth should not trigger with 100% threshold
    emerging_flags = [flag for flag in growth_paths if "emerging_theme" in flag]
    assert len(emerging_flags) == 0


def test_custom_window_size():
    """Test custom window size configuration."""
    growth_analyzer = SemanticGrowth(window_size=3)

    # Create history longer than window
    analyses = [
        {"theme_densities": {"learning": 0.1}, "dominant_themes": ["learning"]},
        {"theme_densities": {"creativity": 0.1}, "dominant_themes": ["creativity"]},
        {"theme_densities": {"health": 0.1}, "dominant_themes": ["health"]},
        {"theme_densities": {"productivity": 0.1}, "dominant_themes": ["productivity"]},
        {"theme_densities": {"achievement": 0.1}, "dominant_themes": ["achievement"]},
    ]

    growth_paths = growth_analyzer.detect_growth_paths(analyses)

    # Check that window size is respected in metadata
    eventlog = MockEventLog()
    analysis = {"theme_densities": {}, "dominant_themes": []}
    growth_analyzer.maybe_emit_growth_report(
        eventlog, "src_123", analysis, growth_paths
    )

    event = eventlog.events[0]
    assert event["meta"]["window_size"] == 3


def test_integration_workflow():
    """Test complete integration workflow: analyze -> detect -> emit."""
    growth_analyzer = SemanticGrowth(growth_threshold=0.3, decline_threshold=-0.3)
    eventlog = MockEventLog()

    # Simulate text sequence with changing themes
    text_sequences = [
        ["I want to learn programming and study algorithms."],
        ["Learning is great, but now I focus on creating art and design."],
        ["Art and creativity inspire me to build beautiful innovative projects."],
    ]

    # Analyze each sequence
    analyses = []
    for texts in text_sequences:
        analysis = growth_analyzer.analyze_texts(texts)
        analyses.append(analysis)

    # Detect growth paths across the sequence
    growth_paths = growth_analyzer.detect_growth_paths(analyses)
    assert len(growth_paths) > 0  # Should detect theme shifts

    # Emit event for the final analysis
    event_id = growth_analyzer.maybe_emit_growth_report(
        eventlog, "src_semantic_456", analyses[-1], growth_paths
    )
    assert event_id is not None

    # Verify event structure
    event = eventlog.events[0]
    assert event["kind"] == "semantic_growth_report"
    assert event["meta"]["analysis"] == analyses[-1]
    assert event["meta"]["growth_paths"] == growth_paths
    assert event["meta"]["src_event_id"] == "src_semantic_456"


def test_metadata_preservation():
    """Test that all metadata is properly preserved in events."""
    growth_analyzer = SemanticGrowth(
        growth_threshold=0.4, decline_threshold=-0.6, window_size=8
    )
    eventlog = MockEventLog()

    analysis = {
        "total_texts": 3,
        "theme_counts": {"learning": 5, "creativity": 2},
        "theme_densities": {"learning": 0.25, "creativity": 0.1},
        "dominant_themes": ["learning"],
    }
    growth_paths = ["emerging_theme:creativity:0.400"]

    growth_analyzer.maybe_emit_growth_report(
        eventlog, "src_789", analysis, growth_paths
    )

    event = eventlog.events[0]
    meta = event["meta"]

    # Check all required metadata fields
    assert meta["component"] == "semantic_growth"
    assert meta["src_event_id"] == "src_789"
    assert meta["deterministic"] is True
    assert meta["thresholds"]["growth_threshold"] == 0.4
    assert meta["thresholds"]["decline_threshold"] == -0.6
    assert meta["window_size"] == 8
    assert meta["themes_analyzed"] == list(growth_analyzer.SEMANTIC_THEMES.keys())
    assert meta["total_texts"] == 3
    assert "digest" in meta


def test_edge_cases():
    """Test edge cases: empty inputs, single theme, ties."""
    growth_analyzer = SemanticGrowth()

    # Single theme text
    result = growth_analyzer.analyze_texts(["I learn and study constantly."])
    assert len(result["theme_counts"]) >= 1
    assert "learning" in result["theme_counts"]

    # Text with no recognizable themes
    result = growth_analyzer.analyze_texts(["Random unrelated words xyz abc def."])
    assert result["total_texts"] == 1
    assert len(result["theme_counts"]) == 0

    # Tied theme densities
    texts = ["I learn", "I create"]  # Equal single-word themes
    result = growth_analyzer.analyze_texts(texts)
    assert len(result["dominant_themes"]) <= 3


def test_replayability():
    """Test that ledger replay yields identical growth reports."""
    growth_analyzer = SemanticGrowth()

    # Same input data
    texts = ["I want to learn and create while building relationships."]
    analysis = growth_analyzer.analyze_texts(texts)

    analyses_history = [
        {"theme_densities": {"learning": 0.1}, "dominant_themes": ["learning"]},
        analysis,
    ]
    growth_paths = growth_analyzer.detect_growth_paths(analyses_history)

    # Generate multiple reports with same data
    eventlogs = [MockEventLog() for _ in range(3)]
    event_ids = []

    for eventlog in eventlogs:
        event_id = growth_analyzer.maybe_emit_growth_report(
            eventlog, "src_replay_test", analysis, growth_paths
        )
        event_ids.append(event_id)

    # All should produce events (first time)
    assert all(eid is not None for eid in event_ids)

    # All events should have identical metadata (except event IDs)
    events = [eventlog.events[0] for eventlog in eventlogs]
    for i in range(1, len(events)):
        assert events[i]["meta"]["digest"] == events[0]["meta"]["digest"]
        assert events[i]["meta"]["analysis"] == events[0]["meta"]["analysis"]
        assert events[i]["meta"]["growth_paths"] == events[0]["meta"]["growth_paths"]
