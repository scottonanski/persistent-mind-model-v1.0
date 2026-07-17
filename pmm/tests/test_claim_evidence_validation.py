from __future__ import annotations

import pytest

from pmm.core.event_log import EventLog
from pmm.core.mirror import Mirror
from pmm.core.schemas import Claim
from pmm.core.validators import validate_claim
from pmm.runtime.loop import RuntimeLoop


def _validate(log: EventLog, evidence_events) -> tuple[bool, str]:
    claim = Claim(
        type="user_preference",
        data={"value": "concise", "evidence_events": evidence_events},
    )
    return validate_claim(claim, log, Mirror(log))


def test_existing_evidence_events_are_accepted() -> None:
    log = EventLog(":memory:")
    first = log.append(kind="user_message", content="one", meta={})
    second = log.append(kind="assistant_message", content="two", meta={})

    ok, _ = _validate(log, [first, second])

    assert ok is True


def test_empty_evidence_list_is_accepted() -> None:
    log = EventLog(":memory:")
    ok, _ = _validate(log, [])
    assert ok is True


def test_duplicate_existing_evidence_ids_are_accepted() -> None:
    log = EventLog(":memory:")
    event_id = log.append(kind="user_message", content="one", meta={})

    ok, _ = _validate(log, [event_id, event_id])

    assert ok is True


def test_missing_evidence_event_rejects_complete_claim() -> None:
    log = EventLog(":memory:")
    ok, reason = _validate(log, [999999])
    assert ok is False
    assert reason == "missing evidence events: 999999"


def test_mixed_existing_and_missing_evidence_rejects_complete_claim() -> None:
    log = EventLog(":memory:")
    event_id = log.append(kind="user_message", content="one", meta={})

    ok, reason = _validate(log, [event_id, 999999, 888888])

    assert ok is False
    assert reason == "missing evidence events: 888888,999999"


@pytest.mark.parametrize("evidence", ["1", [0], [-1], [True], ["1"]])
def test_malformed_evidence_references_are_rejected(evidence) -> None:
    log = EventLog(":memory:")
    ok, reason = _validate(log, evidence)
    assert ok is False
    assert reason


def test_claim_cannot_cite_its_own_eventual_event_id() -> None:
    log = EventLog(":memory:")
    log.append(kind="user_message", content="history", meta={})
    eventual_claim_event_id = log.count() + 1

    ok, reason = _validate(log, [eventual_claim_event_id])

    assert ok is False
    assert reason == f"missing evidence events: {eventual_claim_event_id}"


def test_runtime_does_not_persist_claim_with_missing_evidence() -> None:
    class MissingEvidenceAdapter:
        def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
            return (
                "Unsupported claim.\n"
                'CLAIM:user_preference={"value":"concise",'
                '"evidence_events":[999999]}'
            )

    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=MissingEvidenceAdapter(), autonomy=False)
    loop.run_turn("make unsupported claim")

    events = log.read_all()
    assert not any(e["kind"] == "claim" for e in events)
    assert not any(
        e["kind"] == "concept_bind_event"
        and "user_preference" in e["content"]
        for e in events
    )
