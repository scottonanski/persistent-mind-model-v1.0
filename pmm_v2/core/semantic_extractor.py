"""Deterministic semantic extraction from structured lines.

No regex, no heuristics. Exact prefixes only.
"""

from __future__ import annotations

import json
from typing import Dict, List, Tuple


def extract_commitments(lines: List[str]) -> List[str]:
    """Return commitment texts for exact COMMIT: prefix lines."""
    return [ln.split("COMMIT:", 1)[1].strip() for ln in lines if ln.startswith("COMMIT:")]


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

