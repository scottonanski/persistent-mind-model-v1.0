from __future__ import annotations

import json

import pytest

from pmm.core.event_log import EventLog
from pmm.core.mirror import Mirror
from pmm.core.schemas import Claim
from pmm.core.validators import validate_claim_detailed
from pmm.runtime.loop import RuntimeLoop
from pmm.runtime.oneshot_cli import run_one_turn


class MissingEvidenceAdapter:
    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return (
            "Attempted grounded claim.\n"
            'CLAIM:user_preference={"value":"concise",'
            '"evidence_events":[999999]}'
        )


@pytest.mark.parametrize(
    ("claim", "expected_code"),
    [
        (
            Claim(
                type="user_preference",
                data={"value": "concise", "evidence_events": [999999]},
            ),
            "MISSING_EVIDENCE",
        ),
        (
            Claim(
                type="identity_proposal",
                data={"token": "", "evidence_events": []},
            ),
            "INVALID_IDENTITY_STRUCTURE",
        ),
        (Claim(type="event_existence", data={"id": 999999}), "MISSING_EVENT"),
        (Claim(type="reference", data={"id": 999999}), "INVALID_REFERENCE"),
    ],
)
def test_detailed_validation_has_stable_failure_codes(claim, expected_code) -> None:
    log = EventLog(":memory:")
    result = validate_claim_detailed(claim, log, Mirror(log))
    assert result.ok is False
    assert result.code == expected_code
    assert result.message


def test_runtime_persists_typed_validation_failure() -> None:
    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=MissingEvidenceAdapter(), autonomy=False)
    loop.run_turn("make claim")

    events = log.read_all()
    assistant_event = next(e for e in events if e["kind"] == "assistant_message")
    failures = [e for e in events if e["kind"] == "validation_failure"]
    assert len(failures) == 1
    failure = failures[0]
    content = json.loads(failure["content"])
    assert content == {
        "claim_type": "user_preference",
        "data": {"value": "concise", "evidence_events": [999999]},
        "reason": "missing evidence events: 999999",
        "reason_code": "MISSING_EVIDENCE",
    }
    assert failure["meta"] == {
        "source": "claim_validator",
        "about_event": assistant_event["id"],
        "claim_type": "user_preference",
        "reason_code": "MISSING_EVIDENCE",
    }
    assert not any(e["kind"] == "claim" for e in events)
    assert any(e["kind"] == "reflection" for e in events)


def test_oneshot_exposes_validation_failures() -> None:
    result = run_one_turn(
        db_path=":memory:",
        prompt="make claim",
        adapter=MissingEvidenceAdapter(),
        include_events=False,
    )

    assert result["claims"] == []
    assert result["validation_failures"] == [
        {
            "event_id": result["validation_failures"][0]["event_id"],
            "claim_type": "user_preference",
            "reason_code": "MISSING_EVIDENCE",
            "reason": "missing evidence events: 999999",
            "data": {"value": "concise", "evidence_events": [999999]},
        }
    ]


def test_valid_claim_emits_no_validation_failure() -> None:
    class ValidAdapter:
        def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
            return 'CLAIM:user_preference={"value":"concise"}'

    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=ValidAdapter(), autonomy=False)
    loop.run_turn("make valid claim")

    events = log.read_all()
    assert any(e["kind"] == "claim" for e in events)
    assert not any(e["kind"] == "validation_failure" for e in events)
