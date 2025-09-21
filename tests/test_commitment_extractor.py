"""Tests for the semantic CommitmentExtractor."""

from __future__ import annotations

from pmm.commitments.extractor import CommitmentExtractor, extract_commitments


class MockEventLog:
    """Minimal event log stub for verifying emission metadata."""

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

    def read_all(self) -> list[dict[str, object]]:  # pragma: no cover - passthrough
        return list(self.events)


def test_detect_intent_open_commitment() -> None:
    extractor = CommitmentExtractor()
    analysis = extractor.detect_intent("I will complete the quarterly report tomorrow.")

    assert analysis["intent"] == "open"
    assert analysis["score"] >= extractor.commit_thresh
    assert analysis["exemplar"]


def test_detect_intent_close_commitment() -> None:
    extractor = CommitmentExtractor()
    analysis = extractor.detect_intent(
        "I have completed this task and I am closing the commitment."
    )

    assert analysis["intent"] == "close"
    assert analysis["score"] >= extractor.commit_thresh


def test_detect_intent_expire_commitment() -> None:
    extractor = CommitmentExtractor()
    analysis = extractor.detect_intent(
        "We can no longer do this goal; it is no longer relevant."
    )

    assert analysis["intent"] == "expire"
    assert analysis["score"] >= extractor.commit_thresh


def test_detect_intent_rejects_neutral_text() -> None:
    extractor = CommitmentExtractor()
    analysis = extractor.detect_intent(
        "The sky is clear and the weather is pleasant today."
    )

    assert analysis["intent"] == "none"
    assert analysis["score"] == 0.0


def test_extract_best_sentence_logs_meta() -> None:
    eventlog = MockEventLog()
    extractor = CommitmentExtractor(eventlog=eventlog)
    text = (
        "The meeting went well. "
        "I will complete this task tomorrow. "
        "Please review the notes."
    )

    best = extractor.extract_best_sentence(text)

    assert best == "I will complete this task tomorrow"
    assert len(eventlog.events) == 1
    meta = eventlog.events[0]["meta"]
    assert meta["intent"] == "open"
    assert meta["score"] >= extractor.commit_thresh
    assert meta["exemplar"]
    assert meta["structure"]


def test_vector_returns_embedding() -> None:
    extractor = CommitmentExtractor()
    vec = extractor._vector("I will send the update.")

    assert isinstance(vec, list)
    assert len(vec) > 0


def test_extract_commitments_batch() -> None:
    texts = [
        "I will complete the quarterly report tomorrow.",
        "I have completed this task and I am closing the commitment.",
        "The sky is blue today.",
    ]

    results = extract_commitments(texts)

    intents = {intent for _, intent, _ in results}
    assert intents == {"open", "close"}


def test_structural_soft_gate_allows_short_commitment() -> None:
    extractor = CommitmentExtractor()
    analysis = extractor.detect_intent("I'll take this on.")

    assert analysis["intent"] == "open"
    assert analysis["score"] >= extractor.commit_thresh
