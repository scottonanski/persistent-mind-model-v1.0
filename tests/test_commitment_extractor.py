"""Tests for the embedding-based CommitmentExtractor."""

from pmm.commitments.extractor import CommitmentExtractor


class MockEventLog:
    """Minimal event log for testing commit extraction emissions."""

    def __init__(self):
        self.events = []
        self._next = 1

    def append(self, kind: str, content: str, meta: dict) -> str:
        event_id = f"event_{self._next}"
        self._next += 1
        self.events.append(
            {"id": event_id, "kind": kind, "content": content, "meta": meta}
        )
        return event_id

    def read_all(self):  # pragma: no cover - passthrough helper
        return self.events


def test_score_detects_open_intent():
    extractor = CommitmentExtractor()
    text = "I will complete the quarterly report tomorrow."
    assert extractor.score(text) >= extractor.commit_thresh


def test_score_rejects_neutral_text():
    extractor = CommitmentExtractor()
    text = "The sky is clear and the weather is nice."
    assert extractor.score(text) < extractor.commit_thresh


def test_extract_best_sentence_logs_meta():
    log = MockEventLog()
    extractor = CommitmentExtractor(eventlog=log)
    text = (
        "The meeting went well. "
        "I will complete this task tomorrow."
        " Please review."
    )

    sentence = extractor.extract_best_sentence(text)
    assert sentence == "I will complete this task tomorrow"
    assert len(log.events) == 1
    meta = log.events[0]["meta"]
    # Test the fields that the code actually produces
    assert meta["extracted_sentence"] == "I will complete this task tomorrow"
    assert meta["score"] >= extractor.commit_thresh
    assert meta["threshold"] == extractor.commit_thresh


def test_vector_returns_embedding():
    extractor = CommitmentExtractor()
    text = "I will send the update."
    vec = extractor._vector(text)
    assert isinstance(vec, list)
    assert len(vec) > 0


def test_detects_close_intent():
    extractor = CommitmentExtractor()
    text = "I finished my goal and am closing the commitment."
    assert extractor.score(text) >= extractor.commit_thresh
