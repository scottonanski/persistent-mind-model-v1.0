# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

import json

from pmm.core.event_log import EventLog
from pmm.core.identity_manager import maybe_append_identity_adoptions


def _append_claim(log: EventLog, claim_type: str, token: str) -> int:
    """Helper to append a validated claim event with structured payload."""
    payload = json.dumps({"token": token}, sort_keys=True, separators=(",", ":"))
    content = f"CLAIM:{claim_type}={payload}"
    return log.append(
        kind="claim",
        content=content,
        meta={"claim_type": claim_type, "validated": True},
    )


def test_identity_adoption_emitted_once_per_token() -> None:
    log = EventLog(":memory:")

    # Proposal, reflective anchor, and ratification for the same identity token.
    proposal_id = _append_claim(log, "identity_proposal", "identity.Echo")
    anchor_id = log.append(
        kind="reflection", content="Consider identity.Echo", meta={}
    )
    ratify_id = _append_claim(log, "identity_ratify", "identity.Echo")

    # First run should emit one identity_adoption event.
    maybe_append_identity_adoptions(log)
    events = [e for e in log.read_all() if e["kind"] == "identity_adoption"]
    assert len(events) == 1

    ev = events[0]
    content = json.loads(ev["content"])
    assert content["token"] == "identity.Echo"
    meta = ev.get("meta") or {}
    assert meta["source"] == "identity_manager"
    assert meta["proposal_event_id"] == proposal_id
    assert meta["anchor_event_id"] == anchor_id
    assert meta["anchor_kind"] == "reflection"
    assert meta["ratify_event_id"] == ratify_id

    # Second run must be idempotent: no additional identity_adoption events.
    maybe_append_identity_adoptions(log)
    events_after = [e for e in log.read_all() if e["kind"] == "identity_adoption"]
    assert len(events_after) == 1


def test_identity_adoption_requires_both_proposal_and_ratify() -> None:
    log = EventLog(":memory:")

    # Only proposal – no ratification.
    _append_claim(log, "identity_proposal", "identity.OnlyProposal")
    maybe_append_identity_adoptions(log)
    assert not any(e["kind"] == "identity_adoption" for e in log.read_all())

    # Only ratification – no proposal.
    log2 = EventLog(":memory:")
    _append_claim(log2, "identity_ratify", "identity.OnlyRatify")
    maybe_append_identity_adoptions(log2)
    assert not any(e["kind"] == "identity_adoption" for e in log2.read_all())


def test_identity_adoption_requires_anchor_between_claims() -> None:
    log = EventLog(":memory:")
    _append_claim(log, "identity_proposal", "identity.NoAnchor")
    _append_claim(log, "identity_ratify", "identity.NoAnchor")

    maybe_append_identity_adoptions(log)

    assert not any(e["kind"] == "identity_adoption" for e in log.read_all())


def test_identity_adoption_requires_proposal_before_ratification() -> None:
    log = EventLog(":memory:")
    _append_claim(log, "identity_ratify", "identity.Reversed")
    log.append(kind="reflection", content="Too late", meta={})
    _append_claim(log, "identity_proposal", "identity.Reversed")

    maybe_append_identity_adoptions(log)

    assert not any(e["kind"] == "identity_adoption" for e in log.read_all())


def test_identity_adoption_accepts_commitment_anchor() -> None:
    log = EventLog(":memory:")
    proposal_id = _append_claim(log, "identity_proposal", "identity.Committed")
    anchor_id = log.append(
        kind="commitment_open",
        content="Evaluate identity.Committed",
        meta={"cid": "identity-test", "origin": "assistant", "source": "assistant"},
    )
    ratify_id = _append_claim(log, "identity_ratify", "identity.Committed")

    maybe_append_identity_adoptions(log)

    adoption = next(e for e in log.read_all() if e["kind"] == "identity_adoption")
    assert adoption["meta"]["proposal_event_id"] == proposal_id
    assert adoption["meta"]["anchor_event_id"] == anchor_id
    assert adoption["meta"]["anchor_kind"] == "commitment_open"
    assert adoption["meta"]["ratify_event_id"] == ratify_id


def test_identity_adoption_ignores_unvalidated_claim_events() -> None:
    log = EventLog(":memory:")
    log.append(
        kind="claim",
        content='CLAIM:identity_proposal={"token":"identity.Unvalidated"}',
        meta={"claim_type": "identity_proposal"},
    )
    log.append(kind="reflection", content="Anchor", meta={})
    _append_claim(log, "identity_ratify", "identity.Unvalidated")

    maybe_append_identity_adoptions(log)

    assert not any(e["kind"] == "identity_adoption" for e in log.read_all())


def test_later_valid_sequence_can_adopt_after_earlier_invalid_sequence() -> None:
    log = EventLog(":memory:")
    _append_claim(log, "identity_ratify", "identity.Eventual")
    proposal_id = _append_claim(log, "identity_proposal", "identity.Eventual")
    anchor_id = log.append(kind="reflection", content="Anchor", meta={})
    ratify_id = _append_claim(log, "identity_ratify", "identity.Eventual")

    maybe_append_identity_adoptions(log)

    adoption = next(e for e in log.read_all() if e["kind"] == "identity_adoption")
    assert adoption["meta"]["proposal_event_id"] == proposal_id
    assert adoption["meta"]["anchor_event_id"] == anchor_id
    assert adoption["meta"]["ratify_event_id"] == ratify_id
