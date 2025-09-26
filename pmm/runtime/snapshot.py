from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class LedgerSnapshot:
    """Immutable view of core ledger state used for runtime caching."""

    events: List[Dict[str, Any]]
    identity: Dict[str, Any]
    self_model: Dict[str, Any]
    ias: float
    gas: float
    stage: str
    stage_snapshot: Dict[str, Any]
    last_event_id: int
