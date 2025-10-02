from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LedgerSnapshot:
    """Immutable view of core ledger state used for runtime caching."""

    events: list[dict[str, Any]]
    identity: dict[str, Any]
    self_model: dict[str, Any]
    ias: float
    gas: float
    stage: str
    stage_snapshot: dict[str, Any]
    last_event_id: int
