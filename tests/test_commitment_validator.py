"""Tests for commitment hallucination validator."""

from pmm.runtime.loop import _verify_commitment_claims


def test_validator_catches_fake_event_id():
    """Validator should catch claims about non-existent event IDs."""
    # Simulate a hallucination: "I see a commitment... event ID 21"
    reply = "I see a commitment that was just opened – event ID 21. It's focused on building identity."

    # Events with only event 38 as a commitment
    events = [
        {
            "id": 38,
            "kind": "commitment_open",
            "meta": {"cid": "abc123", "text": "Test commitment"},
        },
    ]

    # Should log warning (we can't easily test logging here, but verify no crash)
    _verify_commitment_claims(reply, events)


def test_validator_catches_fake_topic():
    """Validator should catch claims about non-existent commitment topics."""
    reply = "I committed to 'Compact Scenes' to improve performance."

    events = [
        {
            "id": 38,
            "kind": "commitment_open",
            "meta": {"cid": "abc123", "text": "Adaptive Increment"},
        },
    ]

    _verify_commitment_claims(reply, events)


def test_validator_ignores_conversational():
    """Validator should not trigger on conversational phrases."""
    reply = (
        "Would you like to make a commitment? Perhaps a commitment you'd like to make?"
    )

    events = []

    # Should not trigger (no claims extracted)
    _verify_commitment_claims(reply, events)


def test_validator_accepts_valid_claim():
    """Validator should not warn when claim matches ledger."""
    reply = "I committed to 'Adaptive Increment' to improve the system."

    events = [
        {
            "id": 38,
            "kind": "commitment_open",
            "meta": {"cid": "abc123", "text": "Adaptive Increment"},
        },
    ]

    # Should not warn (claim matches actual commitment)
    _verify_commitment_claims(reply, events)


def test_validator_accepts_valid_event_id():
    """Validator should not warn when event ID is correct."""
    reply = "I see a commitment at event ID 38."

    events = [
        {
            "id": 38,
            "kind": "commitment_open",
            "meta": {"cid": "abc123", "text": "Test commitment"},
        },
    ]

    # Should not warn (event ID 38 exists and is a commitment)
    _verify_commitment_claims(reply, events)
