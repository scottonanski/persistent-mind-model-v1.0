from __future__ import annotations

import pytest

from pmm.core.event_log import EventLog
from pmm.core.mirror import Mirror
from pmm.core.schemas import Claim
from pmm.core.validators import validate_claim
from pmm.runtime.loop import RuntimeLoop


@pytest.mark.parametrize(
    "claim",
    [
        Claim(type="identity_proposal", data={"token": "identity.TestSelf"}),
        Claim(
            type="identity_proposal",
            data={
                "token": "identity.TestSelf",
                "description": "A persistent identity",
                "evidence_events": [],
            },
        ),
        Claim(type="identity_ratify", data={"token": "identity.TestSelf"}),
    ],
)
def test_valid_identity_claim_structures_are_accepted(claim) -> None:
    log = EventLog(":memory:")
    ok, _ = validate_claim(claim, log, Mirror(log))
    assert ok is True


@pytest.mark.parametrize(
    "claim",
    [
        Claim(type="identity_proposal", data={}),
        Claim(type="identity_proposal", data={"token": ""}),
        Claim(type="identity_proposal", data={"token": "   "}),
        Claim(type="identity_proposal", data={"token": 7}),
        Claim(type="identity_proposal", data="identity.TestSelf"),  # type: ignore[arg-type]
        Claim(
            type="identity_proposal",
            data={"token": "identity.TestSelf", "description": ""},
        ),
        Claim(
            type="identity_proposal",
            data={"token": "identity.TestSelf", "evidence_events": "1"},
        ),
        Claim(
            type="identity_proposal",
            data={"token": "identity.TestSelf", "evidence_events": [0, True, "1"]},
        ),
        Claim(
            type="identity_proposal",
            data={"token": "identity.TestSelf", "unexpected": True},
        ),
        Claim(
            type="identity_ratify",
            data={"token": "identity.TestSelf", "description": "not allowed"},
        ),
    ],
)
def test_malformed_identity_claim_structures_are_rejected(claim) -> None:
    log = EventLog(":memory:")
    ok, reason = validate_claim(claim, log, Mirror(log))
    assert ok is False
    assert reason


def test_invalid_identity_claim_does_not_persist_or_trigger_adoption() -> None:
    class InvalidIdentityAdapter:
        def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
            return (
                'CLAIM:identity_proposal={"token":"identity.Invalid",'
                '"unsupported":true}\n'
                'CLAIM:identity_ratify={"token":"identity.Invalid"}'
            )

    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=InvalidIdentityAdapter(), autonomy=False)
    loop.run_turn("attempt invalid identity")

    events = log.read_all()
    claims = [e for e in events if e["kind"] == "claim"]
    assert len(claims) == 1
    assert claims[0]["meta"]["claim_type"] == "identity_ratify"
    assert not any(e["kind"] == "identity_adoption" for e in events)


def test_unknown_non_identity_claim_remains_backward_compatible() -> None:
    log = EventLog(":memory:")
    claim = Claim(type="user_preference", data={"value": "concise"})
    ok, reason = validate_claim(claim, log, Mirror(log))
    assert ok is True
    assert reason == "unknown claim type"
