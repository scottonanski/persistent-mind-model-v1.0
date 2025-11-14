# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/coherence/coherence_scorer.py
"""Coherence scoring and event content building."""

from __future__ import annotations

from typing import Any, Dict, List

from pmm.coherence.claim_parser import ParsedClaim
from pmm.coherence.fragmentation_detector import Conflict


def calculate_coherence_score(
    claims: List[ParsedClaim], conflicts: List[Conflict]
) -> float:
    """Calculate coherence score: higher conflicts -> lower score."""
    if not claims:
        return 1.0
    score = max(0.0, 1.0 - (len(conflicts) / len(claims)))
    return score


def build_coherence_check_content(
    claims: List[ParsedClaim], conflicts: List[Conflict]
) -> Dict[str, Any]:
    """Build content for coherence_check event."""
    domains = list(set(c.domain for c in claims))
    domains.sort()

    serialized_conflicts = [
        {
            "domain": c.domain,
            "claim_a_event": c.claim_a.event_id,
            "claim_b_event": c.claim_b.event_id,
            "severity": c.severity,
        }
        for c in conflicts
    ]

    score = calculate_coherence_score(claims, conflicts)
    resolution_needed = len(conflicts) > 0

    return {
        "check_type": "claim_consistency",
        "scope": domains,
        "conflicts": serialized_conflicts,
        "coherence_score": score,
        "resolution_needed": resolution_needed,
    }
