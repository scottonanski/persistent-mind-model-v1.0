# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/core/semantic_extractor.py
"""Deterministic semantic extraction from structured lines.

No regex, no heuristics. Exact prefixes only.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

COMMITMENT_OUTCOME_PREFIX = "COMMITMENT_OUTCOME:"
COMMITMENT_REVIEW_PREFIX = "COMMITMENT_REVIEW:"


def extract_commitments(lines: List[str]) -> List[str]:
    """Return commitment texts for exact COMMIT: prefix lines."""
    return [
        ln.split("COMMIT:", 1)[1].strip() for ln in lines if ln.startswith("COMMIT:")
    ]


def extract_claims(lines: List[str]) -> List[Tuple[str, Dict]]:
    """Return (type, data) tuples for CLAIM:<type>=<json> lines.

    Raises ValueError on invalid JSON.
    """
    out: List[Tuple[str, Dict]] = []
    for ln in lines:
        if ln.startswith("CLAIM:"):
            type_, raw = ln.split("=", 1)
            type_ = type_.removeprefix("CLAIM:").strip()
            data = json.loads(raw)
            out.append((type_, data))
    return out


def extract_closures(lines: List[str]) -> List[str]:
    """Return CID texts for exact CLOSE: prefix lines."""
    return [ln.split("CLOSE:", 1)[1].strip() for ln in lines if ln.startswith("CLOSE:")]


def extract_reflect(lines: List[str]) -> Dict[str, Any] | None:
    """Return parsed JSON dict for the first REFLECT: line, or None if none or invalid."""
    for ln in lines:
        if ln.startswith("REFLECT:"):
            j = ln[len("REFLECT:") :]
            try:
                parsed = json.loads(j)
                # Must be a dict; reject strings, lists, etc.
                return parsed if isinstance(parsed, dict) else None
            except Exception:
                return None
    return None


def _extract_json_candidates(
    lines: List[str], prefix: str
) -> List[Tuple[str, Dict[str, Any] | None]]:
    """Parse each exact-prefix line independently, preserving malformed payloads."""

    candidates: List[Tuple[str, Dict[str, Any] | None]] = []
    for line in lines:
        if not line.startswith(prefix):
            continue
        raw = line[len(prefix) :]
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            parsed = None
        candidates.append((raw, parsed if isinstance(parsed, dict) else None))
    return candidates


def extract_commitment_outcomes(
    lines: List[str],
) -> List[Tuple[str, Dict[str, Any] | None]]:
    """Return every exact COMMITMENT_OUTCOME candidate without batch fail-open."""

    return _extract_json_candidates(lines, COMMITMENT_OUTCOME_PREFIX)


def extract_commitment_reviews(
    lines: List[str],
) -> List[Tuple[str, Dict[str, Any] | None]]:
    """Return every exact COMMITMENT_REVIEW candidate without batch fail-open."""

    return _extract_json_candidates(lines, COMMITMENT_REVIEW_PREFIX)
