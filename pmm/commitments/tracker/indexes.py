"""Derived indexes over commitment events (Stage 2 scaffolding).

Pure helpers that compute materialized views from a flat event stream. These
do not mutate the ledger and have no side effects. They are intended to be
used by higher-level APIs or the legacy tracker during incremental migration.

Behavioral notes (aligned with CONTRIBUTING):
- Deterministic: results depend only on the provided events list.
- Idempotent: recompute yields the same view; no in-place edits.
- No env gates: fixed semantics regardless of environment.

Invariants:
- Open set = opens minus subsequent closes/expires per cid.
- Close/Expire maps retain the most recent occurrence (last-wins by id).
- Snooze map holds max(until_tick) per cid.
- Due emitted set contains cids already marked as due.
"""

from __future__ import annotations

from collections.abc import Iterable


def build_open_index(events: Iterable[dict]) -> dict[str, dict]:
    """Return a cid -> meta map for currently open commitments.

    A commitment is considered open if the stream contains a `commitment_open`
    for cid with no later `commitment_close` or `commitment_expire` for the
    same cid. The first seen `commitment_open` meta for a cid is retained.
    """
    open_map: dict[str, dict] = {}
    closed: set[str] = set()
    for ev in events:
        kind = ev.get("kind") or ""
        m = ev.get("meta") or {}
        if kind == "commitment_open":
            cid = str(m.get("cid") or "")
            if not cid or cid in closed:
                continue
            if cid not in open_map:
                open_map[cid] = dict(m)
        elif kind in {"commitment_close", "commitment_expire"}:
            cid = str(m.get("cid") or "")
            if cid:
                closed.add(cid)
                open_map.pop(cid, None)
    return open_map


def build_close_index(events: Iterable[dict]) -> dict[str, dict]:
    """Return a cid -> meta map for closed commitments (last close wins)."""
    closed: dict[str, dict] = {}
    for ev in events:
        if (ev.get("kind") or "") == "commitment_close":
            m = ev.get("meta") or {}
            cid = str(m.get("cid") or "")
            if cid:
                closed[cid] = dict(m)
    return closed


def build_expire_index(events: Iterable[dict]) -> dict[str, dict]:
    """Return a cid -> meta map for expired commitments (last expire wins)."""
    expired: dict[str, dict] = {}
    for ev in events:
        if (ev.get("kind") or "") == "commitment_expire":
            m = ev.get("meta") or {}
            cid = str(m.get("cid") or "")
            if cid:
                expired[cid] = dict(m)
    return expired


def build_snooze_index(events: Iterable[dict]) -> dict[str, int]:
    """Return cid -> max(until_tick) for snoozed commitments."""
    out: dict[str, int] = {}
    for ev in events:
        if (ev.get("kind") or "") != "commitment_snooze":
            continue
        m = ev.get("meta") or {}
        cid = str(m.get("cid") or "")
        try:
            until_t = int(m.get("until_tick") or 0)
        except Exception:
            until_t = 0
        if cid:
            out[cid] = max(out.get(cid, 0), until_t)
    return out


def build_due_emitted_set(events: Iterable[dict]) -> set[str]:
    """Return set of cids for which `commitment_due` has been emitted."""
    return set(
        str((ev.get("meta") or {}).get("cid") or "")
        for ev in events
        if (ev.get("kind") or "") == "commitment_due"
    )


__all__ = [
    "build_open_index",
    "build_close_index",
    "build_expire_index",
    "build_snooze_index",
    "build_due_emitted_set",
]
