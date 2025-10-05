"""Commitments tracker API (Stage 1 scaffolding).

This module anchors the API surface described in the tracker split plan. It is
not used by the runtime yet and exists only to make the future migration
incremental and low-risk.
"""

from __future__ import annotations

from typing import Any


def not_ready(
    *_args: Any, **_kwargs: Any
) -> None:  # pragma: no cover - scaffolding only
    """Temporary no-op placeholder for the tracker API."""
    return None


__all__ = [
    "not_ready",
]
