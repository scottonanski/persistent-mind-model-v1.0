"""Deterministic reflection composition for PMM."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pmm.core.schemas import Claim


@dataclass
class TurnDelta:
    opened: List[str] = field(default_factory=list)
    closed: List[str] = field(default_factory=list)
    failed_claims: List[Claim] = field(default_factory=list)
    reflect_block: Optional[Dict] = None

    def is_empty(self) -> bool:
        return not (
            self.opened or self.closed or self.failed_claims or self.reflect_block
        )


def build_reflection_text(delta: TurnDelta) -> str:
    """Compose a concise, deterministic reflection text from the delta.

    Order:
    1) Corrections from failed claims
    2) Opened commitments summary
    3) Closed commitments summary
    4) REFLECT block (observations/next)
    """
    parts: List[str] = []

    if delta.failed_claims:
        types = ", ".join(sorted({c.type for c in delta.failed_claims}))
        parts.append(f"Corrections: invalid claims detected ({types}).")

    if delta.opened:
        parts.append(f"Opened commitments: {', '.join(sorted(delta.opened))}.")

    if delta.closed:
        parts.append(f"Closed commitments: {', '.join(sorted(delta.closed))}.")

    if delta.reflect_block:
        obs = delta.reflect_block.get("observations") or []
        nxt = delta.reflect_block.get("next") or []
        corr = delta.reflect_block.get("corrections") or []
        if obs:
            parts.append("Observations: " + "; ".join(map(str, obs)) + ".")
        if corr:
            parts.append("Corrections: " + "; ".join(map(str, corr)) + ".")
        if nxt:
            parts.append("Next: " + "; ".join(map(str, nxt)) + ".")

    return "\n".join(parts) if parts else ""
