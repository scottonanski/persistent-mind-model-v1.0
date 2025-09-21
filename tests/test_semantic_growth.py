"""Tests for the embedding-backed SemanticGrowth implementation."""

from __future__ import annotations

from pmm.runtime.semantic.semantic_growth import (
    SEMANTIC_THRESHOLD,
    SemanticGrowth,
    detect_growth_themes,
)


class MockEventLog:
    """Minimal in-memory event log for exercising report emission."""

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []
        self._next = 1

    def append(self, kind: str, content: str, meta: dict) -> str:
        event_id = f"event_{self._next}"
        self._next += 1
        self.events.append(
            {"id": event_id, "kind": kind, "content": content, "meta": meta}
        )
        return event_id

    def read_all(self) -> list[dict[str, object]]:
        return list(self.events)


def test_analyze_texts_empty_payload() -> None:
    analyzer = SemanticGrowth()

    result = analyzer.analyze_texts([])
    assert result["total_texts"] == 0
    assert result["theme_scores"] == {}
    assert result["dominant_themes"] == []
    assert (
        result["analysis_metadata"]["semantic_threshold"] == analyzer.semantic_threshold
    )


def test_analyze_texts_detects_semantic_themes() -> None:
    analyzer = SemanticGrowth()
    texts = [
        "Learning new skills keeps my identity evolving.",
        "Friendship and family bond mean everything to me.",
        "I reflect on the meaning of life when setting goals.",
        "Artistic expression fuels my imagination for creating something new.",
        "Overcoming obstacles with persistence builds strength through struggle.",
    ]

    analysis = analyzer.analyze_texts(texts)

    assert analysis["total_texts"] == len(texts)
    for theme in ("growth", "relationships", "purpose", "creativity", "resilience"):
        assert theme in analysis["theme_scores"], f"expected {theme} in theme_scores"
        assert analysis["theme_scores"][theme] >= SEMANTIC_THRESHOLD

    assert len(analysis["dominant_themes"]) <= 3
    assert analysis["reflections"][0]["themes"]["growth"] >= SEMANTIC_THRESHOLD


def test_detect_growth_paths_flags_changes() -> None:
    analyzer = SemanticGrowth(growth_threshold=0.3, decline_threshold=-0.3)
    baseline = {
        "theme_scores": {"growth": 0.2, "resilience": 0.5},
        "dominant_themes": ["resilience"],
    }
    current = {
        "theme_scores": {"growth": 0.5, "resilience": 0.1},
        "dominant_themes": ["growth"],
    }

    flags = analyzer.detect_growth_paths([baseline, current])

    assert "emerging_theme:growth:1.500" in flags
    assert "declining_theme:resilience:-0.800" in flags
    assert "new_dominant_theme:growth" in flags
    assert "lost_dominant_theme:resilience" in flags


def test_maybe_emit_growth_report_idempotent() -> None:
    analyzer = SemanticGrowth()
    eventlog = MockEventLog()
    reflections = [
        "Learning new skills keeps my identity evolving.",
        "Friendship and family bond mean everything to me.",
    ]
    analysis = analyzer.analyze_texts(reflections)
    growth_paths = analyzer.detect_growth_paths([analysis, analysis])

    first_id = analyzer.maybe_emit_growth_report(
        eventlog, src_event_id="src_1", analysis=analysis, growth_paths=growth_paths
    )
    assert first_id is not None

    second_id = analyzer.maybe_emit_growth_report(
        eventlog, src_event_id="src_1", analysis=analysis, growth_paths=growth_paths
    )
    assert second_id is None
    assert len(eventlog.read_all()) == 1


def test_detect_growth_themes_filters_empty_inputs() -> None:
    reflections = [
        "Learning new skills keeps my identity evolving.",
        "",
        None,
        "Artistic expression fuels my imagination for creating something new.",
    ]

    scored = detect_growth_themes(reflections)

    assert len(scored) == 2
    texts = [item[0] for item in scored]
    assert all(text for text in texts)
    assert scored[0][1]
    assert scored[1][1]
