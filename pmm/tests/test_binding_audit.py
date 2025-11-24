# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

from pmm.core.event_log import EventLog
from pmm.core.concept_graph import ConceptGraph
from pmm.tools.binding_audit import (
    BindingGap,
    audit_bindings,
    backfill_bindings,
)


def test_audit_detects_missing_claim_binding() -> None:
    log = EventLog(":memory:")
    # Append a claim without any binding
    claim_id = log.append(
        kind="claim", content='CLAIM:identity.name={"value":"Echo"}', meta={}
    )

    gaps = audit_bindings(log)
    assert gaps == [
        BindingGap(
            event_id=claim_id, token="identity.name", reason="claim_missing_binding"
        )
    ], "Expected a single gap for the unbound claim"

    # Backfill and verify binding is created
    appended_ids = backfill_bindings(log, gaps)
    assert len(appended_ids) == 1

    cg = ConceptGraph(log)
    cg.rebuild(log.read_all())
    assert claim_id in cg.events_for_concept("identity.name")


def test_audit_noop_when_binding_exists() -> None:
    log = EventLog(":memory:")
    claim_id = log.append(
        kind="claim", content='CLAIM:policy.update={"value":"foo"}', meta={}
    )
    bind_content = (
        '{"event_id":%d,"relation":"describes","tokens":["policy.update"]}' % claim_id
    )
    log.append(
        kind="concept_bind_event",
        content=bind_content,
        meta={"source": "test"},
    )

    gaps = audit_bindings(log)
    assert gaps == []

    appended_ids = backfill_bindings(log, gaps)
    assert appended_ids == []


def test_audit_identity_policy_commitment_bindings() -> None:
    log = EventLog(":memory:")
    # identity event with meta token
    id_evt = log.append(
        kind="assistant_message",
        content="identity set",
        meta={"identity_token": "identity.self"},
    )
    # policy event
    pol_evt = log.append(
        kind="policy_update", content="p", meta={"policy_token": "policy.core"}
    )
    # commitment open with cid
    cid = "c123"
    comm_evt = log.append(
        kind="commitment_open", content="c", meta={"cid": cid, "text": "t"}
    )

    gaps = audit_bindings(log)
    # Should surface three gaps with appropriate reasons
    gap_map = {(g.event_id, g.token, g.reason) for g in gaps}
    assert (id_evt, "identity.self", "identity") in gap_map
    assert (pol_evt, "policy.core", "policy") in gap_map
    assert (comm_evt, f"commitment.{cid}", "commitment") in gap_map

    appended_ids = backfill_bindings(log, gaps)
    assert len(appended_ids) == 3

    cg = ConceptGraph(log)
    cg.rebuild(log.read_all())
    assert id_evt in cg.events_for_concept("identity.self")
    assert pol_evt in cg.events_for_concept("policy.core")
    assert comm_evt in cg.events_for_concept(f"commitment.{cid}")
