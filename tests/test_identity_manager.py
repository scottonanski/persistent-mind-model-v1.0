# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

import json

from pmm.core.event_log import EventLog
from pmm.core.identity_adoption import (
    IDENTITY_SUBJECT_ID_V1,
    identity_anchor_meta,
)
from pmm.core.identity_manager import maybe_append_identity_adoptions


def _claim_content(claim_type: str, token: str = "identity.Echo") -> str:
    payload = {"subject_id": IDENTITY_SUBJECT_ID_V1, "token": token}
    return f"CLAIM:{claim_type}={json.dumps(payload, sort_keys=True, separators=(',', ':'))}"


def _append_claim(
    log: EventLog,
    claim_type: str,
    token: str,
    origin_event_id: int,
) -> int:
    return log.append(
        kind="claim",
        content=_claim_content(claim_type, token),
        meta={
            "claim_type": claim_type,
            "validated": True,
            "origin_event_id": origin_event_id,
        },
    )


def _append_anchor(log: EventLog, token: str, proposal_event_id: int) -> int:
    return log.append(
        kind="reflection",
        content=json.dumps(
            {
                "proposal_event_id": proposal_event_id,
                "reason": "identity_proposal_anchor",
                "subject_id": IDENTITY_SUBJECT_ID_V1,
                "token": token,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        meta={
            "identity_anchor": identity_anchor_meta(
                token=token,
                subject_id=IDENTITY_SUBJECT_ID_V1,
                proposal_event_id=proposal_event_id,
            )
        },
    )


def _v1_chain(log: EventLog, token: str = "identity.Echo") -> tuple[int, int, int]:
    first_assistant = log.append(
        kind="assistant_message",
        content=_claim_content("identity_proposal", token),
        meta={"role": "assistant"},
    )
    proposal_id = _append_claim(log, "identity_proposal", token, first_assistant)
    anchor_id = _append_anchor(log, token, proposal_id)
    second_assistant = log.append(
        kind="assistant_message",
        content=_claim_content("identity_ratify", token),
        meta={"role": "assistant"},
    )
    ratify_id = _append_claim(log, "identity_ratify", token, second_assistant)
    return proposal_id, anchor_id, ratify_id


def test_identity_adoption_emitted_once_per_token() -> None:
    log = EventLog(":memory:")
    proposal_id, anchor_id, ratify_id = _v1_chain(log)

    maybe_append_identity_adoptions(log)
    events = [e for e in log.read_all() if e["kind"] == "identity_adoption"]
    assert len(events) == 1

    ev = events[0]
    content = json.loads(ev["content"])
    assert content["token"] == "identity.Echo"
    assert content["subject_id"] == IDENTITY_SUBJECT_ID_V1
    meta = ev.get("meta") or {}
    assert meta["source"] == "identity_manager"
    assert meta["adoption_protocol"] == "r06.v1"
    assert meta["proposal_event_id"] == proposal_id
    assert meta["anchor_event_id"] == anchor_id
    assert meta["anchor_kind"] == "reflection"
    assert meta["ratify_event_id"] == ratify_id

    maybe_append_identity_adoptions(log)
    events_after = [e for e in log.read_all() if e["kind"] == "identity_adoption"]
    assert len(events_after) == 1


def test_identity_adoption_requires_both_proposal_and_ratify() -> None:
    log = EventLog(":memory:")
    assistant = log.append(
        kind="assistant_message", content="propose", meta={"role": "assistant"}
    )
    proposal_id = _append_claim(log, "identity_proposal", "identity.OnlyProposal", assistant)
    _append_anchor(log, "identity.OnlyProposal", proposal_id)
    maybe_append_identity_adoptions(log)
    assert not any(e["kind"] == "identity_adoption" for e in log.read_all())

    log2 = EventLog(":memory:")
    assistant2 = log2.append(
        kind="assistant_message", content="ratify", meta={"role": "assistant"}
    )
    _append_claim(log2, "identity_ratify", "identity.OnlyRatify", assistant2)
    maybe_append_identity_adoptions(log2)
    assert not any(e["kind"] == "identity_adoption" for e in log2.read_all())


def test_identity_adoption_requires_v1_anchor_between_claims() -> None:
    log = EventLog(":memory:")
    first = log.append(
        kind="assistant_message", content="propose", meta={"role": "assistant"}
    )
    _append_claim(log, "identity_proposal", "identity.NoAnchor", first)
    second = log.append(
        kind="assistant_message", content="ratify", meta={"role": "assistant"}
    )
    _append_claim(log, "identity_ratify", "identity.NoAnchor", second)
    maybe_append_identity_adoptions(log)
    assert not any(e["kind"] == "identity_adoption" for e in log.read_all())


def test_identity_adoption_rejects_commitment_anchor() -> None:
    log = EventLog(":memory:")
    first = log.append(
        kind="assistant_message", content="propose", meta={"role": "assistant"}
    )
    proposal_id = _append_claim(log, "identity_proposal", "identity.Committed", first)
    log.append(
        kind="commitment_open",
        content="Evaluate identity.Committed",
        meta={"cid": "identity-test", "origin": "assistant", "source": "assistant"},
    )
    second = log.append(
        kind="assistant_message", content="ratify", meta={"role": "assistant"}
    )
    _append_claim(log, "identity_ratify", "identity.Committed", second)
    maybe_append_identity_adoptions(log)
    assert not any(e["kind"] == "identity_adoption" for e in log.read_all())
    assert proposal_id > 0


def test_identity_adoption_requires_later_assistant_ratify() -> None:
    log = EventLog(":memory:")
    assistant = log.append(
        kind="assistant_message", content="same reply", meta={"role": "assistant"}
    )
    proposal_id = _append_claim(log, "identity_proposal", "identity.SameReply", assistant)
    _append_anchor(log, "identity.SameReply", proposal_id)
    _append_claim(log, "identity_ratify", "identity.SameReply", assistant)
    maybe_append_identity_adoptions(log)
    assert not any(e["kind"] == "identity_adoption" for e in log.read_all())


def test_identity_adoption_ignores_unvalidated_claim_events() -> None:
    log = EventLog(":memory:")
    first = log.append(
        kind="assistant_message", content="propose", meta={"role": "assistant"}
    )
    log.append(
        kind="claim",
        content=_claim_content("identity_proposal", "identity.Unvalidated"),
        meta={"claim_type": "identity_proposal"},
    )
    log.append(kind="reflection", content="Anchor", meta={})
    second = log.append(
        kind="assistant_message", content="ratify", meta={"role": "assistant"}
    )
    _append_claim(log, "identity_ratify", "identity.Unvalidated", second)
    maybe_append_identity_adoptions(log)
    assert first > 0
    assert not any(e["kind"] == "identity_adoption" for e in log.read_all())


def test_later_valid_sequence_can_adopt_after_earlier_invalid_sequence() -> None:
    log = EventLog(":memory:")
    first = log.append(
        kind="assistant_message", content="early ratify", meta={"role": "assistant"}
    )
    _append_claim(log, "identity_ratify", "identity.Eventual", first)
    proposal_id, anchor_id, ratify_id = _v1_chain(log, "identity.Eventual")
    maybe_append_identity_adoptions(log)
    adoption = next(e for e in log.read_all() if e["kind"] == "identity_adoption")
    assert adoption["meta"]["proposal_event_id"] == proposal_id
    assert adoption["meta"]["anchor_event_id"] == anchor_id
    assert adoption["meta"]["ratify_event_id"] == ratify_id


def test_later_valid_sequence_can_adopt_after_forged_actor_chain() -> None:
    log = EventLog(":memory:")
    token = "identity.EventualActor"
    unrelated = log.append(
        kind="assistant_message", content="not a claim", meta={"role": "assistant"}
    )
    forged_proposal = _append_claim(log, "identity_proposal", token, unrelated)
    _append_anchor(log, token, forged_proposal)
    forged_ratify_origin = log.append(
        kind="assistant_message", content="still not a claim", meta={"role": "assistant"}
    )
    _append_claim(log, "identity_ratify", token, forged_ratify_origin)

    proposal_id, anchor_id, ratify_id = _v1_chain(log, token)
    maybe_append_identity_adoptions(log)

    adoption = next(e for e in log.read_all() if e["kind"] == "identity_adoption")
    assert adoption["meta"]["proposal_event_id"] == proposal_id
    assert adoption["meta"]["anchor_event_id"] == anchor_id
    assert adoption["meta"]["ratify_event_id"] == ratify_id
