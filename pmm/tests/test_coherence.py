# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/tests/test_coherence.py
"""Tests for coherence subsystem."""


from pmm.coherence.claim_parser import ParsedClaim, extract_all_claims
from pmm.coherence.coherence_scorer import (
    build_coherence_check_content,
    calculate_coherence_score,
)
from pmm.coherence.fragmentation_detector import Conflict, detect_fragmentation
from pmm.coherence.reconciliation_engine import (
    propose_reconciliation_actions,
)
from pmm.core.event_log import EventLog


def test_extract_all_claims():
    """Test structured claim extraction."""
    log = EventLog(":memory:")
    log.append(
        kind="claim",
        content='CLAIM:memory={"domain": "memory", "value": "short_term"}',
    )
    log.append(
        kind="user_message",
        content='CLAIM:invalid={"bad": "json"}',  # Ignored
    )

    claims = extract_all_claims(log)
    assert len(claims) == 1
    assert claims[0] == ParsedClaim(1, "memory", "memory", "short_term")


def test_detect_fragmentation():
    """Test conflict detection."""
    claims = [
        ParsedClaim(1, "mem", "memory", "short"),
        ParsedClaim(2, "mem", "memory", "long"),
        ParsedClaim(3, "sys", "system", "enabled"),
        ParsedClaim(4, "sys", "system", "disabled"),
    ]

    conflicts = detect_fragmentation(claims)
    assert len(conflicts) == 2
    assert conflicts[0].domain == "memory"
    assert conflicts[0].severity == "medium"
    assert conflicts[1].domain == "system"
    assert conflicts[1].severity == "high"


def test_calculate_coherence_score():
    """Test coherence scoring."""
    claims = [ParsedClaim(1, "t", "d", "v")] * 4
    conflicts = [Conflict("d", claims[0], claims[1], "medium")]

    score = calculate_coherence_score(claims, conflicts)
    assert score == 1.0 - 1 / 4  # 0.75

    score_no_conflicts = calculate_coherence_score(claims, [])
    assert score_no_conflicts == 1.0


def test_build_coherence_check_content():
    """Test event content building."""
    claims = [ParsedClaim(1, "t", "d", "v")]
    conflicts = []

    content = build_coherence_check_content(claims, conflicts)
    assert content["coherence_score"] == 1.0
    assert not content["resolution_needed"]


def test_propose_reconciliation_actions():
    """Test reconciliation proposals."""
    conflict = Conflict(
        "d", ParsedClaim(1, "t", "d", "v1"), ParsedClaim(2, "t", "d", "v2"), "medium"
    )
    actions = propose_reconciliation_actions([conflict])

    assert len(actions) == 1
    assert actions[0].action_type == "deprecate_both"
    assert actions[0].conflict == conflict
