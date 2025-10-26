"""Tests for commitment hallucination validator."""

from __future__ import annotations

from uuid import uuid4

from pmm.runtime.loop import _verify_commitment_claims
from pmm.storage.eventlog import EventLog


def _build_eventlog(tmp_path, events: list[dict]) -> EventLog:
    """Create a real EventLog populated with the provided events."""
    db_path = tmp_path / f"ledger_{uuid4().hex}.db"
    log = EventLog(str(db_path))
    for ev in events:
        kind = ev["kind"]
        content = ev.get("content", "")
        meta = ev.get("meta", {})
        log.append(kind=kind, content=content, meta=meta)
    return log


def test_validator_catches_fake_event_id(tmp_path):
    """Validator should catch claims about non-existent event IDs."""
    reply = (
        "I see a commitment that was just opened – event ID 21. "
        "It's focused on building identity."
    )

    eventlog = _build_eventlog(
        tmp_path,
        [
            {
                "kind": "commitment_open",
                "content": "Commitment opened: Test commitment",
                "meta": {"cid": "abc123", "text": "Test commitment"},
            }
        ],
    )

    assert _verify_commitment_claims(reply, eventlog) is True


def test_validator_catches_fake_topic(tmp_path):
    """Validator should catch claims about non-existent commitment topics."""
    reply = "I committed to compact scenes."

    eventlog = _build_eventlog(
        tmp_path,
        [
            {
                "kind": "commitment_open",
                "content": "Commitment opened: Adaptive Increment",
                "meta": {"cid": "abc123", "text": "Adaptive Increment"},
            }
        ],
    )

    assert _verify_commitment_claims(reply, eventlog) is True


def test_validator_ignores_conversational(tmp_path):
    """Validator should not trigger on conversational phrases."""
    reply = (
        "Would you like to make a commitment? Perhaps a commitment you'd like to make?"
    )

    eventlog = _build_eventlog(tmp_path, [])

    assert _verify_commitment_claims(reply, eventlog) is False


def test_validator_accepts_valid_claim(tmp_path):
    """Validator should not warn when claim matches ledger."""
    reply = "I committed to 'Adaptive Increment' to improve the system."

    eventlog = _build_eventlog(
        tmp_path,
        [
            {
                "kind": "commitment_open",
                "content": "Commitment opened: Adaptive Increment",
                "meta": {"cid": "abc123", "text": "Adaptive Increment"},
            }
        ],
    )

    assert _verify_commitment_claims(reply, eventlog) is False


def test_validator_accepts_valid_event_id(tmp_path):
    """Validator should not warn when event ID is correct."""
    eventlog = _build_eventlog(
        tmp_path,
        [
            {
                "kind": "commitment_open",
                "content": "Commitment opened: Test commitment",
                "meta": {"cid": "abc123", "text": "Test commitment"},
            }
        ],
    )
    actual_id = eventlog.read_all()[-1]["id"]
    reply = f"I see a commitment at event ID {actual_id}."

    assert _verify_commitment_claims(reply, eventlog) is False
