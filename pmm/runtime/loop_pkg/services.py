"""Runtime loop services container (Stage 1 scaffolding).

The goal of this module is to provide explicit dependency wiring for the
runtime loop to avoid hidden import cycles when we extract scheduler, pipeline,
and IO/metrics layers. For Stage 1, we keep this as a light placeholder to
minimize risk.

Do not import this module from runtime code paths yet; it is not used.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LoopServices:
    """Typed container for loop dependencies (placeholder).

    This is intentionally minimal for Stage 1. Fields will be filled in as the
    split progresses (eventlog, snapshot/projections, metrics, bridge, tracker,
    trace buffer, etc.), with concrete types added under TYPE_CHECKING as
    needed to prevent import-time cycles.
    """

    # Placeholders for future wiring
    eventlog: object | None = None
    metrics: object | None = None
    bridge: object | None = None
    tracker: object | None = None


__all__ = [
    "LoopServices",
]
