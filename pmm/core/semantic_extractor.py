# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/core/semantic_extractor.py
"""Deterministic semantic extraction from structured lines.

No regex, no heuristics. Exact prefixes only.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple


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
