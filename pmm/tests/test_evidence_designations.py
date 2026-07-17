from __future__ import annotations

import json

import pytest

from pmm.core.event_log import EventLog
from pmm.core.validators import validate_evidence_designations
from pmm.retrieval.pipeline import RetrievalResult
from pmm.runtime.loop import RuntimeLoop


class ReplyAdapter:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return self.reply


def _run_turn(monkeypatch, reply: str, selected: list[int]):
    log = EventLog(":memory:")
    for event_id in selected:
        while log.count() < event_id:
            log.append(kind="test_event", content="selected evidence", meta={})

    result = RetrievalResult(
        event_ids=selected,
        relevant_cids=[],
        active_concepts=[],
        provenance={
            event_id: {"reasons": ["test"], "scores": {}}
            for event_id in selected
        },
    )
    monkeypatch.setattr(
        "pmm.runtime.loop.run_retrieval_pipeline", lambda **kwargs: result
    )
    RuntimeLoop(
        eventlog=log, adapter=ReplyAdapter(reply), autonomy=False
    ).run_turn("test")
    return log.read_all()


def _assistant(events):
    return next(event for event in events if event["kind"] == "assistant_message")


def test_absent_designations_and_event_numbers_in_prose_are_not_formal(monkeypatch):
    events = _run_turn(monkeypatch, "Event 107 supports this conclusion.", [])

    assert "evidence_designations" not in _assistant(events)["meta"]
    assert not any(event["kind"] == "validation_failure" for event in events)


def test_broken_first_line_json_is_ordinary_prose(monkeypatch):
    events = _run_turn(
        monkeypatch,
        '{"evidence_designations":[{"event_id":1}\nordinary prose',
        [],
    )

    assert "evidence_designations" not in _assistant(events)["meta"]
    assert not any(event["kind"] == "validation_failure" for event in events)


def test_empty_designations_are_valid(monkeypatch):
    events = _run_turn(monkeypatch, '{"evidence_designations":[]}\nNo evidence.', [])

    assert _assistant(events)["meta"]["evidence_designations_validated"] is True
    assert _assistant(events)["meta"]["evidence_designations"] == []
    assert not any(event["kind"] == "validation_failure" for event in events)


def test_selected_designation_is_attached_before_assistant_append(monkeypatch):
    events = _run_turn(
        monkeypatch,
        '{"evidence_designations":[{"event_id":1,'
        '"supports":"  retrieval_notice_failed  "}]}\nSupported.',
        [1],
    )

    assert _assistant(events)["meta"]["evidence_designations"] == [
        {"event_id": 1, "supports": "retrieval_notice_failed"}
    ]
    assert not any(event["kind"] == "validation_failure" for event in events)


def test_unselected_designation_rejects_complete_array(monkeypatch):
    events = _run_turn(
        monkeypatch,
        '{"evidence_designations":['
        '{"event_id":1,"supports":"selected"},'
        '{"event_id":2,"supports":"unselected"}]}\nMixed.',
        [1],
    )

    assistant = _assistant(events)
    assert "evidence_designations" not in assistant["meta"]
    failure = next(event for event in events if event["kind"] == "validation_failure")
    assert failure["id"] > assistant["id"]
    assert failure["meta"] == {
        "source": "evidence_designation_validator",
        "about_event": assistant["id"],
        "reason_code": "EVIDENCE_NOT_SELECTED",
    }
    assert json.loads(failure["content"])["reason"] == (
        "designated evidence events were not selected for this turn: 2"
    )


@pytest.mark.parametrize(
    "value",
    [
        {},
        ["bad"],
        [{"event_id": True, "supports": "x"}],
        [{"event_id": 0, "supports": "x"}],
        [{"event_id": 1, "supports": " "}],
        [{"event_id": 1, "supports": "x", "extra": "bad"}],
        [
            {"event_id": 1, "supports": "x"},
            {"event_id": 1, "supports": " x "},
        ],
    ],
)
def test_malformed_designation_structures_are_rejected(value):
    result, canonical = validate_evidence_designations(value, [1])

    assert result.ok is False
    assert result.code == "INVALID_EVIDENCE_DESIGNATION_STRUCTURE"
    assert canonical == []


def test_claim_evidence_must_be_selected(monkeypatch):
    reply = 'CLAIM:user_preference={"value":"concise","evidence_events":[1]}'

    selected_events = _run_turn(monkeypatch, reply, [1])
    assert any(event["kind"] == "claim" for event in selected_events)

    unselected_events = _run_turn(monkeypatch, reply, [])
    assert not any(event["kind"] == "claim" for event in unselected_events)
    failure = next(
        event for event in unselected_events if event["kind"] == "validation_failure"
    )
    assert failure["meta"]["reason_code"] == "EVIDENCE_NOT_SELECTED"


def test_existing_but_unselected_claim_evidence_is_rejected(monkeypatch):
    log = EventLog(":memory:")
    evidence_id = log.append(kind="test_event", content="existing", meta={})
    result = RetrievalResult(event_ids=[], relevant_cids=[], active_concepts=[])
    monkeypatch.setattr(
        "pmm.runtime.loop.run_retrieval_pipeline", lambda **kwargs: result
    )
    reply = (
        'CLAIM:user_preference={"value":"concise",'
        f'"evidence_events":[{evidence_id}]}}'
    )
    RuntimeLoop(
        eventlog=log, adapter=ReplyAdapter(reply), autonomy=False
    ).run_turn("test")

    events = log.read_all()
    assert not any(event["kind"] == "claim" for event in events)
    failure = next(event for event in events if event["kind"] == "validation_failure")
    assert failure["meta"]["reason_code"] == "EVIDENCE_NOT_SELECTED"
    assert json.loads(failure["content"])["reason"] == (
        f"evidence events were not selected for this turn: {evidence_id}"
    )
