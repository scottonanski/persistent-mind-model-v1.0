"""Tests for the semantic prioritizer."""

from __future__ import annotations

from pmm.runtime.prioritizer import Prioritizer, detect_urgency, rank_commitments


class MockEventLog:
    """Minimal event log stub for verifying metadata outputs."""

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


def test_detect_urgency_high_level() -> None:
    analysis = detect_urgency(
        "This must be done immediately, it cannot wait any longer."
    )

    assert analysis["level"] == "high"
    assert analysis["score"] >= 0.7
    assert analysis["exemplar"]


def test_detect_urgency_synonymic_phrase() -> None:
    analysis = detect_urgency("We really need to push this out right away.")

    assert analysis["level"] == "high"
    assert analysis["score"] >= 0.7


def test_prioritize_commitments_includes_urgency_metadata() -> None:
    prioritizer = Prioritizer()
    commitments = [
        {
            "cid": "c-high",
            "text": "This must be done immediately, it cannot wait any longer.",
            "status": "open",
            "created_at": "2024-01-01T00:00:00+00:00",
        },
        {
            "cid": "c-low",
            "text": "This can wait until I have some free time.",
            "status": "open",
            "created_at": "2024-01-01T00:00:00+00:00",
        },
    ]

    prioritized = prioritizer.prioritize_commitments(commitments)

    assert prioritized[0]["cid"] == "c-high"
    assert prioritized[0]["urgency"]["level"] == "high"
    assert prioritized[0]["urgency"]["exemplar"]


def test_prioritize_commitments_logs_event() -> None:
    eventlog = MockEventLog()
    prioritizer = Prioritizer(eventlog=eventlog)
    commitments = [
        {
            "cid": "c1",
            "text": "We should handle this in the next few days.",
            "status": "open",
            "created_at": "2024-01-05T00:00:00+00:00",
        }
    ]

    prioritizer.prioritize_commitments(commitments)

    assert len(eventlog.events) == 1
    meta = eventlog.events[0]["meta"]
    assert meta["commitment_count"] == 1
    assert meta["top_urgency"]["level"] in {"medium", "high", "low", "none"}


def test_rank_commitments_uses_semantic_urgency() -> None:
    events = [
        {
            "kind": "commitment_open",
            "meta": {"cid": "c1", "text": "This must be done immediately."},
            "ts": "2024-01-01T00:00:00+00:00",
        },
        {
            "kind": "commitment_open",
            "meta": {"cid": "c2", "text": "This can wait until later."},
            "ts": "2024-01-01T00:00:00+00:00",
        },
    ]

    ranked = rank_commitments(events)

    assert ranked[0][0] == "c1"
    assert ranked[0][1] >= ranked[1][1]
