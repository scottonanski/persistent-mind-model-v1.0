# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Test that valid claims are persisted to the ledger."""

from pmm.core.event_log import EventLog
from pmm.runtime.loop import RuntimeLoop


class NameClaimAdapter:
    """Adapter that generates a name_change claim."""

    deterministic_latency_ms = 0
    model = "test"

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return (
            "Hello! I accept the name Echo.\n\n"
            'CLAIM:name_change={"old_name":"Assistant","new_name":"Echo","timestamp":"2025-11-10T12:00:00Z"}'
        )


def test_valid_claim_persisted_to_ledger():
    """Test that valid claims are written to ledger as claim events."""
    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=NameClaimAdapter(), autonomy=False)

    # Run a turn that generates a name claim
    loop.run_turn("Your name is Echo")

    # Check that a claim event was created
    events = log.read_all()
    claim_events = [e for e in events if e.get("kind") == "claim"]

    assert len(claim_events) == 1, "Expected exactly one claim event"

    claim = claim_events[0]
    assert claim["content"].startswith("CLAIM:name_change=")
    assert "Echo" in claim["content"]

    meta = claim.get("meta", {})
    assert meta.get("claim_type") == "name_change"
    assert meta.get("validated") is True


def test_identity_claims_in_context():
    """Test that identity claims appear in context after being persisted."""
    from pmm.runtime.context_builder import build_context

    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=NameClaimAdapter(), autonomy=False)

    # Run a turn that generates a name claim
    loop.run_turn("Your name is Echo")

    # Build context and verify identity appears
    context = build_context(log, limit=5)

    assert "Identity:" in context, "Identity block should be in context"
    assert "name: Echo" in context, "Name should be in identity block"


def test_failed_claim_not_persisted():
    """Test that failed claims are not persisted to ledger."""

    class FailedClaimAdapter:
        deterministic_latency_ms = 0
        model = "test"

        def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
            # Invalid claim: references non-existent event
            return 'CLAIM:event_existence={"id":99999}'

    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=FailedClaimAdapter(), autonomy=False)

    loop.run_turn("test")

    # Check that no claim events were created
    events = log.read_all()
    claim_events = [e for e in events if e.get("kind") == "claim"]

    assert len(claim_events) == 0, "Failed claims should not be persisted"
