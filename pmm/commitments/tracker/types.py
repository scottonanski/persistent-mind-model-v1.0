"""Commitments types scaffolding (Stage 1/2).

Defines typed models and status enums for commitments. This module is not yet
used by the legacy tracker; it exists to enable incremental migration without
behavior changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CommitmentStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    EXPIRED = "expired"
    SNOOZED = "snoozed"


@dataclass(frozen=True)
class Commitment:
    cid: str
    text: str
    status: CommitmentStatus = CommitmentStatus.OPEN
    due_ts: int | None = None
    source: str | None = None


__all__ = ["CommitmentStatus", "Commitment"]
