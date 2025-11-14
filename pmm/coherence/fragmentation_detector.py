# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/coherence/fragmentation_detector.py
"""Fragmentation detection via conflict analysis."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import List

from pmm.coherence.claim_parser import ParsedClaim


@dataclass(frozen=True)
class Conflict:
    domain: str
    claim_a: ParsedClaim
    claim_b: ParsedClaim
    severity: str  # "low", "medium", "high"


def detect_fragmentation(claims: List[ParsedClaim]) -> List[Conflict]:
    """Detect conflicts within domains.

    Conflicts if different values in same domain.
    Severity: 'high' for enabled/disabled, 'medium' otherwise.
    """
    by_domain = defaultdict(list)
    for claim in claims:
        by_domain[claim.domain].append(claim)

    conflicts = []
    for domain, domain_claims in by_domain.items():
        for i in range(len(domain_claims)):
            for j in range(i + 1, len(domain_claims)):
                a, b = domain_claims[i], domain_claims[j]
                if a.value != b.value:
                    severity = (
                        "high"
                        if {a.value, b.value} == {"enabled", "disabled"}
                        else "medium"
                    )
                    conflicts.append(Conflict(domain, a, b, severity))

    # Sort deterministically: by domain, then event_ids
    conflicts.sort(key=lambda c: (c.domain, c.claim_a.event_id, c.claim_b.event_id))
    return conflicts
