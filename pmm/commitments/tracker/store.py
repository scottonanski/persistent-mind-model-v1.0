"""Commitment store snapshot (Stage 2 scaffolding).

Builds a deterministic snapshot of commitments state from a flat event list.
This is read-only scaffolding that does not mutate the ledger. The goal is to
offer a typed, cohesive view usable by APIs while legacy code migrates.

Replay guarantees:
- Full recompute from the event list yields the same state as incremental updates.
- No in-place mutation; callers must treat returned objects as immutable snapshots.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .indexes import (
    build_close_index,
    build_due_emitted_set,
    build_expire_index,
    build_open_index,
    build_snooze_index,
)


@dataclass(frozen=True)
class Store:
    """Materialized commitments snapshot.

    - open: current open commitments (cid -> meta)
    - closed: last close meta per cid (cid -> meta)
    - expired: last expire meta per cid (cid -> meta)
    - snoozed_until: cid -> max until_tick
    - due_emitted: set of cids that already have a `commitment_due`
    """

    open: dict[str, dict]
    closed: dict[str, dict]
    expired: dict[str, dict]
    snoozed_until: dict[str, int]
    due_emitted: set[str]


def build_store(events: Iterable[dict]) -> Store:
    """Construct and return a Store snapshot from events."""
    evs: list[dict] = list(events)
    return Store(
        open=build_open_index(evs),
        closed=build_close_index(evs),
        expired=build_expire_index(evs),
        snoozed_until=build_snooze_index(evs),
        due_emitted=build_due_emitted_set(evs),
    )


__all__ = ["Store", "build_store"]
