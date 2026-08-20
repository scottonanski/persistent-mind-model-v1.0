# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

import json

import pytest

from pmm.core.concept_graph import ConceptGraph
from pmm.core.event_log import EventLog, IdentityAdoptionRejected
from pmm.core.identity_adoption import (
    ADOPTION_PROTOCOL_V1,
    IDENTITY_ADOPTION_REASON_V1,
    IDENTITY_ADOPTION_VALIDATOR_SOURCE,
    IDENTITY_SUBJECT_ID_V1,
    canonical_identity_adoption_content,
    identity_anchor_meta,
)
from pmm.core.identity_manager import maybe_append_identity_adoptions
from pmm.core.meme_graph import MemeGraph


def _claim_content(claim_type: str, token: str) -> str:
    payload = {"subject_id": IDENTITY_SUBJECT_ID_V1, "token": token}
    return f"CLAIM:{claim_type}={json.dumps(payload, sort_keys=True, separators=(',', ':'))}"


def _v1_chain(log: EventLog, token: str = "identity.Echo") -> dict[str, int]:
    first = log.append(
        kind="assistant_message",
        content=_claim_content("identity_proposal", token),
        meta={"role": "assistant"},
    )
    proposal_id = log.append(
        kind="claim",
        content=_claim_content("identity_proposal", token),
        meta={
            "claim_type": "identity_proposal",
            "validated": True,
            "origin_event_id": first,
        },
    )
    anchor_id = log.append(
        kind="reflection",
        content="identity anchor",
        meta={
            "identity_anchor": identity_anchor_meta(
                token=token,
                subject_id=IDENTITY_SUBJECT_ID_V1,
                proposal_event_id=proposal_id,
            )
        },
    )
    second = log.append(
        kind="assistant_message",
        content=_claim_content("identity_ratify", token),
        meta={"role": "assistant"},
    )
    ratify_id = log.append(
        kind="claim",
        content=_claim_content("identity_ratify", token),
        meta={
            "claim_type": "identity_ratify",
            "validated": True,
            "origin_event_id": second,
        },
    )
    return {
        "proposal": proposal_id,
        "anchor": anchor_id,
        "ratify": ratify_id,
        "proposal_origin": first,
        "ratify_origin": second,
    }


def _adoption_meta(chain: dict[str, int]) -> dict:
    return {
        "adoption_protocol": ADOPTION_PROTOCOL_V1,
        "proposal_event_id": chain["proposal"],
        "anchor_event_id": chain["anchor"],
        "anchor_kind": "reflection",
        "ratify_event_id": chain["ratify"],
        "proposal_origin_event_id": chain["proposal_origin"],
        "ratify_origin_event_id": chain["ratify_origin"],
    }


def test_direct_append_of_valid_chain_uses_same_boundary() -> None:
    log = EventLog(":memory:")
    chain = _v1_chain(log)
    event_id, created = log.append_identity_adoption(
        content=canonical_identity_adoption_content(
            token="identity.Echo", subject_id=IDENTITY_SUBJECT_ID_V1
        ),
        meta=_adoption_meta(chain),
    )
    assert created is True
    event = log.get(event_id)
    assert event is not None
    assert event["kind"] == "identity_adoption"
    assert event["meta"]["adoption_protocol"] == ADOPTION_PROTOCOL_V1


def test_generic_append_rejects_invalid_adoption_and_records_failure() -> None:
    log = EventLog(":memory:")
    with pytest.raises(IdentityAdoptionRejected, match="identity_adoption rejected") as caught:
        log.append(
            kind="identity_adoption",
            content=json.dumps({"token": "identity.Echo"}),
            meta={},
        )
    failures = [e for e in log.read_all() if e["kind"] == "validation_failure"]
    assert len(failures) == 1
    assert caught.value.failure_event_id == failures[0]["id"]
    assert caught.value.reason_code == "INVALID_IDENTITY_ADOPTION_STRUCTURE"
    assert caught.value.canonical_commit_succeeded is True
    content = json.loads(failures[0]["content"])
    assert content["validation_type"] == "identity_adoption"
    assert "attempted_content" in content
    assert "attempted_meta" in content
    assert content["attempted_digest"]
    assert content["reason_code"] == "INVALID_IDENTITY_ADOPTION_STRUCTURE"
    assert failures[0]["meta"]["source"] == IDENTITY_ADOPTION_VALIDATOR_SOURCE

    with pytest.raises(IdentityAdoptionRejected, match="identity_adoption rejected") as repeated:
        log.append(
            kind="identity_adoption",
            content=json.dumps({"token": "identity.Echo"}),
            meta={},
        )
    assert len([e for e in log.read_all() if e["kind"] == "validation_failure"]) == 1
    assert repeated.value.failure_event_id == failures[0]["id"]


def test_v1_uniqueness_is_idempotent_and_non_reopenable() -> None:
    log = EventLog(":memory:")
    chain = _v1_chain(log)
    first_id, created = log.append_identity_adoption(
        content=canonical_identity_adoption_content(
            token="identity.Echo", subject_id=IDENTITY_SUBJECT_ID_V1
        ),
        meta=_adoption_meta(chain),
    )
    assert created is True
    second_id, created_again = log.append_identity_adoption(
        content=canonical_identity_adoption_content(
            token="identity.Echo", subject_id=IDENTITY_SUBJECT_ID_V1
        ),
        meta=_adoption_meta(chain),
    )
    assert created_again is False
    assert second_id == first_id
    assert len([e for e in log.read_all() if e["kind"] == "identity_adoption"]) == 1


def test_does_not_trust_validated_true_without_reparsing() -> None:
    log = EventLog(":memory:")
    first = log.append(
        kind="assistant_message",
        content='CLAIM:identity_proposal={"token":"identity.Echo"}',
        meta={"role": "assistant"},
    )
    forged_proposal = log.append(
        kind="claim",
        content='CLAIM:identity_proposal={"token":"identity.Echo"}',
        meta={
            "claim_type": "identity_proposal",
            "validated": True,
            "origin_event_id": first,
        },
    )
    anchor_id = log.append(
        kind="reflection",
        content="anchor",
        meta={
            "identity_anchor": identity_anchor_meta(
                token="identity.Echo",
                subject_id=IDENTITY_SUBJECT_ID_V1,
                proposal_event_id=forged_proposal,
            )
        },
    )
    second = log.append(
        kind="assistant_message",
        content=_claim_content("identity_ratify", "identity.Echo"),
        meta={"role": "assistant"},
    )
    ratify_id = log.append(
        kind="claim",
        content=_claim_content("identity_ratify", "identity.Echo"),
        meta={
            "claim_type": "identity_ratify",
            "validated": True,
            "origin_event_id": second,
        },
    )
    with pytest.raises(IdentityAdoptionRejected, match="identity_adoption rejected"):
        log.append(
            kind="identity_adoption",
            content=canonical_identity_adoption_content(
                token="identity.Echo", subject_id=IDENTITY_SUBJECT_ID_V1
            ),
            meta={
                "adoption_protocol": ADOPTION_PROTOCOL_V1,
                "proposal_event_id": forged_proposal,
                "anchor_event_id": anchor_id,
                "anchor_kind": "reflection",
                "ratify_event_id": ratify_id,
                "proposal_origin_event_id": first,
                "ratify_origin_event_id": second,
            },
        )
    failure = next(e for e in log.read_all() if e["kind"] == "validation_failure")
    assert json.loads(failure["content"])["reason_code"] == "INVALID_ADOPTION_REFERENT_KIND"


def test_origin_must_have_emitted_the_exact_identity_claim() -> None:
    log = EventLog(":memory:")
    chain = _v1_chain(log)
    unrelated = log.append(
        kind="assistant_message", content="no identity claim here", meta={"role": "assistant"}
    )
    meta = _adoption_meta(chain)
    meta["proposal_origin_event_id"] = unrelated
    proposal = log.get(chain["proposal"])
    assert proposal is not None
    proposal["meta"]["origin_event_id"] = unrelated
    with log._lock:
        log._conn.execute(
            "UPDATE events SET meta = ? WHERE id = ?",
            (json.dumps(proposal["meta"], sort_keys=True, separators=(",", ":")), chain["proposal"]),
        )
        log._conn.commit()

    event_id, created = log.append_identity_adoption(
        content=canonical_identity_adoption_content(
            token="identity.Echo", subject_id=IDENTITY_SUBJECT_ID_V1
        ),
        meta=meta,
    )
    assert event_id is None
    assert created is False
    failure = [e for e in log.read_all() if e["kind"] == "validation_failure"][-1]
    assert json.loads(failure["content"])["reason_code"] == "IDENTITY_ACTOR_INVALID"


def test_adoption_revalidates_proposal_evidence_references() -> None:
    log = EventLog(":memory:")
    token = "identity.Echo"
    proposal_payload = {
        "evidence_events": [999],
        "subject_id": IDENTITY_SUBJECT_ID_V1,
        "token": token,
    }
    proposal_content = (
        "CLAIM:identity_proposal="
        + json.dumps(proposal_payload, sort_keys=True, separators=(",", ":"))
    )
    first = log.append(
        kind="assistant_message", content=proposal_content, meta={"role": "assistant"}
    )
    proposal = log.append(
        kind="claim",
        content=proposal_content,
        meta={
            "claim_type": "identity_proposal",
            "validated": True,
            "origin_event_id": first,
        },
    )
    anchor = log.append(
        kind="reflection",
        content="identity anchor",
        meta={
            "identity_anchor": identity_anchor_meta(
                token=token,
                subject_id=IDENTITY_SUBJECT_ID_V1,
                proposal_event_id=proposal,
            )
        },
    )
    second = log.append(
        kind="assistant_message",
        content=_claim_content("identity_ratify", token),
        meta={"role": "assistant"},
    )
    ratify = log.append(
        kind="claim",
        content=_claim_content("identity_ratify", token),
        meta={
            "claim_type": "identity_ratify",
            "validated": True,
            "origin_event_id": second,
        },
    )
    event_id, created = log.append_identity_adoption(
        content=canonical_identity_adoption_content(
            token=token, subject_id=IDENTITY_SUBJECT_ID_V1
        ),
        meta={
            "adoption_protocol": ADOPTION_PROTOCOL_V1,
            "proposal_event_id": proposal,
            "anchor_event_id": anchor,
            "anchor_kind": "reflection",
            "ratify_event_id": ratify,
            "proposal_origin_event_id": first,
            "ratify_origin_event_id": second,
        },
    )
    assert event_id is None
    assert created is False
    failure = [e for e in log.read_all() if e["kind"] == "validation_failure"][-1]
    assert json.loads(failure["content"])["reason_code"] == "INVALID_IDENTITY_EVIDENCE"


def test_legacy_adoption_is_history_only_and_does_not_block_v1() -> None:
    log = EventLog(":memory:")
    legacy_content = json.dumps(
        {"reason": IDENTITY_ADOPTION_REASON_V1, "token": "identity.Echo"},
        sort_keys=True,
        separators=(",", ":"),
    )
    with log._lock:
        log._conn.execute(
            "INSERT INTO events (ts, kind, content, meta, prev_hash, hash) "
            "VALUES (?, 'identity_adoption', ?, ?, ?, ?)",
            (
                "2020-01-01T00:00:00.000000Z",
                legacy_content,
                json.dumps({"source": "identity_manager"}),
                None,
                "legacy-identity-echo",
            ),
        )
        log._conn.commit()

    concepts = ConceptGraph(log)
    concepts.rebuild()
    assert concepts.events_for_concept("identity.Echo") == []
    assert concepts.concept_kind("identity.Echo") == ""

    graph = MemeGraph(log)
    graph.rebuild(log.read_all())
    legacy = next(e for e in log.read_all() if e["kind"] == "identity_adoption")
    assert graph.graph.has_node(legacy["id"])
    assert list(graph.graph.out_edges(legacy["id"])) == []

    chain = _v1_chain(log)
    maybe_append_identity_adoptions(log)
    v1_rows = [
        e
        for e in log.read_all()
        if e["kind"] == "identity_adoption"
        and (e.get("meta") or {}).get("adoption_protocol") == ADOPTION_PROTOCOL_V1
    ]
    assert len(v1_rows) == 1
    assert json.loads(v1_rows[0]["content"])["token"] == "identity.Echo"
    assert chain["proposal"] < v1_rows[0]["id"]


def test_projections_rebuild_and_incremental_use_recorded_anchor() -> None:
    log = EventLog(":memory:")
    chain = _v1_chain(log)
    later_assistant = log.append(
        kind="assistant_message", content="later", meta={"role": "assistant"}
    )
    later_reflection = log.append(kind="reflection", content="unrelated", meta={})
    adoption_id, _ = log.append_identity_adoption(
        content=canonical_identity_adoption_content(
            token="identity.Echo", subject_id=IDENTITY_SUBJECT_ID_V1
        ),
        meta=_adoption_meta(chain),
    )

    rebuilt = MemeGraph(log)
    rebuilt.rebuild(log.read_all())
    edge = list(rebuilt.graph.out_edges(adoption_id, data=True))
    assert len(edge) == 1
    assert edge[0][1] == chain["anchor"]
    assert edge[0][2]["label"] == "adopts_identity_for"
    assert later_assistant not in {edge[0][1]}
    assert later_reflection not in {edge[0][1]}

    incremental = MemeGraph(log)
    for event in log.read_all():
        incremental.add_event(event)
    inc_edge = list(incremental.graph.out_edges(adoption_id, data=True))
    assert inc_edge[0][1] == chain["anchor"]

    concepts_rebuilt = ConceptGraph(log)
    concepts_rebuilt.rebuild()
    assert adoption_id in concepts_rebuilt.events_for_concept("identity.Echo")
    assert concepts_rebuilt.concept_kind("identity.Echo") == "identity"

    concepts_incremental = ConceptGraph(log)
    for event in log.read_all():
        concepts_incremental.sync(event)
    assert adoption_id in concepts_incremental.events_for_concept("identity.Echo")
    assert concepts_incremental.concept_kind("identity.Echo") == "identity"
