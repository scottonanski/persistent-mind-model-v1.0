# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/context/semantic_tagger.py
"""Deterministic semantic tagging from event content.

No heuristics; uses structured extractors only.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pmm.core.semantic_extractor import extract_claims, extract_commitments


def extract_semantic_tags(event: Dict[str, Any]) -> List[str]:
    """Extract semantic tags from event content using structured parsing.

    Returns sorted list of tags for determinism.
    """
    tags: List[str] = []
    content = event.get("content", "")
    lines = content.splitlines()

    # Commitments
    if extract_commitments(lines):
        tags.append("commitment")

    # Claims
    try:
        if extract_claims(lines):
            tags.append("claim")
    except ValueError:
        # Invalid JSON; no tag
        pass

    # Reflections: check event kind, as reflections are structured events
    if event.get("kind") == "reflection":
        tags.append("reflection")

    return sorted(tags)
