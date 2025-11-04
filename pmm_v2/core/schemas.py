"""Core schemas for PMM v2.

Defines lightweight data structures used across the runtime. Kept minimal
and implementation-agnostic to preserve determinism and clarity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Event:
    """Canonical event record stored in the EventLog."""

    id: Optional[int]
    ts: str
    kind: str
    content: str
    meta: Dict[str, Any] = field(default_factory=dict)
    prev_hash: Optional[str] = None
    hash: Optional[str] = None


@dataclass
class Claim:
    """Structured claim made by the model, for future validation."""

    type: str
    data: Dict[str, Any]
