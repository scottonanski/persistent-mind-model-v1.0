"""Tests for the embedding-backed stance filter."""

from __future__ import annotations

from pmm.runtime.filters.stance_filter import (
    STANCE_THRESHOLD,
    StanceFilter,
    batch_detect_stance,
    detect_stance,
    score_stances,
)


class MockEventLog:
    """Minimal append/read event log used in stance filter tests."""

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


def test_analyze_commitment_text_empty_payload() -> None:
    stance_filter = StanceFilter()

    result = stance_filter.analyze_commitment_text("")
    assert result["primary_stance"] == {"label": "neutral", "score": 0.0}
    assert result["detected_stances"] == {}
    assert result["stance_scores"] == {}


def test_analyze_commitment_text_detects_stances() -> None:
    stance_filter = StanceFilter()
    text = "I'm just joking around and making a joke because it's lighthearted and fun."

    result = stance_filter.analyze_commitment_text(text)

    assert result["primary_stance"]["label"] == "playful"
    assert result["primary_stance"]["score"] >= STANCE_THRESHOLD
    assert "playful" in result["detected_stances"]
    assert result["detected_stances"]["playful"] == result["primary_stance"]["score"]


def test_score_and_detect_stance_api() -> None:
    text = "Let's break this down with logical reasoning step by step."
    scores = score_stances(text)
    assert set(scores.keys()) >= {"analytical", "serious"}

    stance, score = detect_stance(text)
    assert stance == "analytical"
    assert score >= STANCE_THRESHOLD


def test_batch_detect_stance_handles_neutral() -> None:
    texts = [
        "",
        "This is important and we must focus on the solemn matter ahead.",
        None,
    ]

    results = batch_detect_stance(texts)
    assert results[0] == ("neutral", 0.0)
    assert results[1][0] == "serious"
    assert results[1][1] >= STANCE_THRESHOLD
    assert results[2] == ("neutral", 0.0)


def test_detect_shifts_contradiction() -> None:
    stance_filter = StanceFilter(shift_window=3)

    playful_analysis = stance_filter.analyze_commitment_text(
        "This is lighthearted and fun, just joking around with friends."
    )
    serious_analysis = stance_filter.analyze_commitment_text(
        "This is important and we must focus; it's a solemn matter."
    )

    shifts = stance_filter.detect_shifts([playful_analysis, serious_analysis])
    assert len(shifts) == 1
    assert any(
        flag.startswith("stance_shift:playful->serious:contradiction")
        for flag in shifts
    )


def test_detect_shifts_change_without_contradiction() -> None:
    stance_filter = StanceFilter(shift_window=3)

    analytical = stance_filter.analyze_commitment_text(
        "Let's break this down with logical reasoning step by step."
    )
    reflective = stance_filter.analyze_commitment_text(
        "I'm thinking deeply and looking back on my choices thoughtfully."
    )

    shifts = stance_filter.detect_shifts([analytical, reflective])
    assert len(shifts) == 1
    assert "stance_shift:analytical->reflective:change" in shifts[0]


def test_maybe_emit_filter_event_idempotent() -> None:
    stance_filter = StanceFilter()
    eventlog = MockEventLog()
    analysis = stance_filter.analyze_commitment_text(
        "I'm thinking deeply and engaging in self-reflection about my choices."
    )
    shifts = []

    first = stance_filter.maybe_emit_filter_event(eventlog, "src_123", analysis, shifts)
    assert first is not None

    duplicate = stance_filter.maybe_emit_filter_event(
        eventlog, "src_123", analysis, shifts
    )
    assert duplicate is None
    assert len(eventlog.read_all()) == 1


def test_digest_serialization_deterministic() -> None:
    stance_filter = StanceFilter()
    analysis = stance_filter.analyze_commitment_text(
        "Let's break this down with logical reasoning."
    )
    shifts = ["stance_shift:analytical->serious:change:positions_0_1"]

    payloads = [stance_filter._serialize_for_digest(analysis, shifts) for _ in range(3)]
    assert payloads[0] == payloads[1] == payloads[2]


def test_end_to_end_workflow() -> None:
    stance_filter = StanceFilter(shift_window=3)
    eventlog = MockEventLog()

    analyses = [
        stance_filter.analyze_commitment_text(
            "I'm just joking around and keeping things lighthearted."
        ),
        stance_filter.analyze_commitment_text(
            "This is important and we must focus on the solemn matter."
        ),
    ]

    shifts = stance_filter.detect_shifts(analyses)
    assert shifts

    event_id = stance_filter.maybe_emit_filter_event(
        eventlog, "src_final", analyses[-1], shifts
    )
    assert event_id is not None

    event = eventlog.read_all()[0]
    assert event["kind"] == "stance_filter_report"
    assert event["meta"]["analysis"] == analyses[-1]
    assert event["meta"]["shifts"] == shifts
    assert event["meta"]["semantic_threshold"] == stance_filter.semantic_threshold
