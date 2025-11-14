# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/coherence/claim_parser.py
"""Structured claim parsing for coherence analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from pmm.core.event_log import EventLog
from pmm.core.semantic_extractor import extract_claims


@dataclass(frozen=True)
class ParsedClaim:
    event_id: int
    claim_type: str
    domain: str
    value: str


def extract_all_claims(log: EventLog) -> List[ParsedClaim]:
    """Extract all claims from event log using structured parsing.

    Maps to ParsedClaim if data contains 'domain' and 'value'.
    """
    claims = []
    for event in log.read_all():
        lines = (event.get("content") or "").splitlines()
        try:
            parsed = extract_claims(lines)
        except ValueError:
            continue  # Invalid JSON, skip
        for claim_type, data in parsed:
            if isinstance(data, dict) and "domain" in data and "value" in data:
                claims.append(
                    ParsedClaim(
                        event_id=event["id"],
                        claim_type=claim_type,
                        domain=data["domain"],
                        value=data["value"],
                    )
                )
    return claims
