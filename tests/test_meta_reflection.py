"""Tests for semantic MetaReflection implementation."""

from __future__ import annotations

from pmm.runtime.meta.meta_reflection import MetaReflection


class MockEventLog:
    """Minimal append/read event log used for report emission tests."""

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


def test_analyze_reflections_empty_summary() -> None:
    meta_reflection = MetaReflection()

    summary = meta_reflection.analyze_reflections([])

    assert summary["reflection_count"] == 0
    assert summary["stance_metrics"]["distribution"] == {}
    assert summary["reflections"] == []


def test_analyze_reflections_semantic_outputs() -> None:
    meta_reflection = MetaReflection()

    events = [
        {
            "id": "r1",
            "kind": "reflection",
            "content": "This is lighthearted and fun, just joking around with friends.",
        },
        {
            "id": "r2",
            "kind": "reflection",
            "content": "Let's break this down logically and analyze it step by step.",
        },
        {
            "id": "r3",
            "kind": "reflection",
            "content": "I feel strongly about this and I am overjoyed.",
        },
        {
            "id": "r4",
            "kind": "reflection",
            "content": "I have learned from past mistakes and my perspective is changing.",
        },
    ]

    summary = meta_reflection.analyze_reflections(events)

    assert summary["reflection_count"] == 4
    stance_labels = summary["stance_metrics"]["distribution"].keys()
    assert {"playful", "analytical", "emotional"}.issubset(stance_labels)

    dimension_metrics = summary["dimension_metrics"]
    assert dimension_metrics["follow_through"]["distribution"].get("high", 0.0) > 0.0
    assert dimension_metrics["evolution"]["distribution"].get("growing", 0.0) > 0.0
    assert summary["reflections"][0]["dimensions"]["depth"]["scores"]


def test_detect_meta_anomalies_flags_conditions() -> None:
    meta_reflection = MetaReflection(bias_threshold=0.7, shallow_threshold=0.6)

    stagnant_text = (
        "This is just a small thought and a surface level reflection. "
        "Maybe someday I might do this but not sure I will follow through. "
        "I feel the same as always and nothing has changed."
    )

    events = [
        {"id": f"r{i}", "kind": "reflection", "content": stagnant_text}
        for i in range(6)
    ]

    summary = meta_reflection.analyze_reflections(events)
    anomalies = meta_reflection.detect_meta_anomalies(summary)

    assert any(flag.startswith("stance_bias:") for flag in anomalies)
    assert any(flag.startswith("shallow_reflection_pattern") for flag in anomalies)
    assert any(flag.startswith("low_follow_through") for flag in anomalies)
    assert any(flag.startswith("stagnant_evolution") for flag in anomalies)


def test_maybe_emit_report_idempotent() -> None:
    meta_reflection = MetaReflection()
    eventlog = MockEventLog()

    events = [
        {
            "id": "r1",
            "kind": "reflection",
            "content": "This is lighthearted and fun, just joking around with friends.",
        },
        {
            "id": "r2",
            "kind": "reflection",
            "content": "I have learned from past mistakes and my perspective is changing.",
        },
    ]

    summary = meta_reflection.analyze_reflections(events)
    first = meta_reflection.maybe_emit_report(eventlog, summary, window="weekly")
    assert first is not None

    duplicate = meta_reflection.maybe_emit_report(eventlog, summary, window="weekly")
    assert duplicate is None
    assert len(eventlog.read_all()) == 1
