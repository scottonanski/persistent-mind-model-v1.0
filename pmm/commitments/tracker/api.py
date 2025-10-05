"""Commitments tracker API scaffolding.

High-level helpers built on top of store + indexes.

Read operations are pure and safe to import during migration — they do not
mutate the ledger or change legacy behavior.

Write operations (v1) delegate to the legacy tracker when available to preserve
idempotency and behavior. Fallbacks perform minimal, deterministic emissions.
"""

from __future__ import annotations

from collections.abc import Iterable

from pmm.storage.eventlog import EventLog

from . import due as _due
from . import indexes as _idx
from . import ttl as _ttl
from .store import Store, build_store

# Optional import of legacy tracker for write behaviors
try:  # pragma: no cover - exercised via integration tests
    from pmm.commitments.tracker import CommitmentTracker as _LegacyTracker
except Exception:  # pragma: no cover
    _LegacyTracker = None  # type: ignore


def _filter_events_window(
    events: Iterable[dict],
    *,
    since_id: int | None = None,
    until_id: int | None = None,
    since_ts: float | None = None,
    until_ts: float | None = None,
) -> list[dict]:
    """Filter events by id and/or timestamp window (inclusive bounds).

    - If both id and ts are provided, both constraints apply (AND).
    - Missing ids/ts are ignored.
    """
    out: list[dict] = []
    for ev in events:
        try:
            eid = int(ev.get("id") or 0)
        except Exception:
            eid = 0
        try:
            ts = float(ev.get("ts")) if ev.get("ts") is not None else None
        except Exception:
            ts = None
        ok = True
        if since_id is not None and eid and eid < int(since_id):
            ok = False
        if until_id is not None and eid and eid > int(until_id):
            ok = False
        if since_ts is not None and ts is not None and ts < float(since_ts):
            ok = False
        if until_ts is not None and ts is not None and ts > float(until_ts):
            ok = False
        if ok:
            out.append(ev)
    return out


def snapshot(events: Iterable[dict]) -> Store:
    """Return a materialized commitments snapshot (pure)."""
    return build_store(events)


def open_commitments(events: Iterable[dict]) -> dict[str, dict]:
    """Return cid -> meta for current open commitments."""
    return _idx.build_open_index(events)


def snoozed_until_tick(events: Iterable[dict]) -> dict[str, int]:
    """Return cid -> until_tick for current snoozes (max per cid)."""
    return _idx.build_snooze_index(events)


def expired_by_hours(
    events: Iterable[dict], *, ttl_hours: int, now_iso: str | None = None
) -> list[tuple[str, int]]:
    """Return list of (cid, -1 placeholder) expired by hours semantics."""
    return _ttl.compute_expired(events, ttl_hours=int(ttl_hours), now_iso=now_iso)


def due_now(
    events: Iterable[dict], *, horizon_hours: int, now_epoch: int
) -> list[tuple[str, int]]:
    """Return list of (cid, due_epoch) for reflection-driven commitments due now."""
    return _due.compute_due(
        events, horizon_hours=int(horizon_hours), now_epoch=int(now_epoch)
    )


__all__ = [
    "Store",
    "snapshot",
    "open_commitments",
    "snoozed_until_tick",
    "expired_by_hours",
    "due_now",
]


# Windowed queries (pure helpers)


def open_effective_at(
    events: Iterable[dict],
    *,
    until_id: int | None = None,
    until_ts: float | None = None,
) -> dict[str, dict]:
    """Return open commitments effective at the end of the window.

    Applies all events up to the inclusive boundary (id and/or ts) and returns
    the open set at that point.
    """
    evs = list(events)
    if until_id is None and until_ts is None:
        return _idx.build_open_index(evs)
    evs2 = _filter_events_window(
        evs, since_id=None, until_id=until_id, since_ts=None, until_ts=until_ts
    )
    return _idx.build_open_index(evs2)


def opens_within(
    events: Iterable[dict],
    *,
    since_id: int | None = None,
    until_id: int | None = None,
    since_ts: float | None = None,
    until_ts: float | None = None,
) -> list[dict]:
    """Return commitment_open events that occurred within the window (inclusive)."""
    evs = _filter_events_window(
        events,
        since_id=since_id,
        until_id=until_id,
        since_ts=since_ts,
        until_ts=until_ts,
    )
    return [e for e in evs if (e.get("kind") or "") == "commitment_open"]


def closes_within(
    events: Iterable[dict],
    *,
    since_id: int | None = None,
    until_id: int | None = None,
    since_ts: float | None = None,
    until_ts: float | None = None,
) -> list[dict]:
    """Return commitment_close events that occurred within the window (inclusive)."""
    evs = _filter_events_window(
        events,
        since_id=since_id,
        until_id=until_id,
        since_ts=since_ts,
        until_ts=until_ts,
    )
    return [e for e in evs if (e.get("kind") or "") == "commitment_close"]


def expires_within(
    events: Iterable[dict],
    *,
    since_id: int | None = None,
    until_id: int | None = None,
    since_ts: float | None = None,
    until_ts: float | None = None,
) -> list[dict]:
    """Return commitment_expire events that occurred within the window (inclusive)."""
    evs = _filter_events_window(
        events,
        since_id=since_id,
        until_id=until_id,
        since_ts=since_ts,
        until_ts=until_ts,
    )
    return [e for e in evs if (e.get("kind") or "") == "commitment_expire"]


__all__.extend(
    [
        "open_effective_at",
        "opens_within",
        "closes_within",
        "expires_within",
    ]
)


# Higher-level filtered views


def open_by_reason(events: Iterable[dict], reason: str) -> dict[str, dict]:
    """Return open commitments whose original open meta has the given reason.

    Reason match is case-sensitive equality on meta['reason'].
    """
    m = _idx.build_open_index(events)
    out: dict[str, dict] = {}
    for cid, meta in m.items():
        if (meta or {}).get("reason") == reason:
            out[cid] = meta
    return out


def open_by_stage(events: Iterable[dict], stage: str) -> dict[str, dict]:
    """Return open commitments whose open meta has the given stage label.

    Stage match is case-sensitive equality on meta['stage'].
    """
    m = _idx.build_open_index(events)
    out: dict[str, dict] = {}
    for cid, meta in m.items():
        if (meta or {}).get("stage") == stage:
            out[cid] = meta
    return out


__all__.extend(
    [
        "open_by_reason",
        "open_by_stage",
    ]
)


# -----------------------
# Write API (facade, v1)
# -----------------------


def add_commitment(
    eventlog: EventLog,
    *,
    text: str,
    source: str | None = None,
    extra_meta: dict | None = None,
    project: str | None = None,
) -> str:
    """Open a new commitment and return its cid.

    Delegates to legacy CommitmentTracker.add_commitment to preserve behavior
    and idempotency rules. Falls back to emitting a minimal commitment_open on
    failure.
    """
    if _LegacyTracker is not None:
        try:
            return _LegacyTracker(eventlog).add_commitment(
                text, source=source, extra_meta=extra_meta, project=project
            )
        except Exception:
            pass
    import uuid as _uuid

    cid = _uuid.uuid4().hex
    meta: dict = {"cid": cid, "text": str(text)}
    if source is not None:
        meta["source"] = str(source)
    if isinstance(extra_meta, dict):
        for k, v in extra_meta.items():
            if k not in meta:
                meta[k] = v
    eventlog.append(
        kind="commitment_open", content=f"Commitment opened: {text}", meta=meta
    )
    return cid


def close_commitment(
    eventlog: EventLog,
    *,
    cid: str,
    evidence_type: str = "done",
    description: str = "",
    artifact: str | None = None,
    events: Iterable[dict] | None = None,
    open_map: dict[str, dict] | None = None,
) -> bool:
    """Close a commitment by cid using legacy evidence rules.

    Delegates to CommitmentTracker.close_with_evidence for parity. Returns
    True on close emitted, False if not applicable.
    """
    if _LegacyTracker is not None:
        try:
            return _LegacyTracker(eventlog).close_with_evidence(
                cid,
                evidence_type=evidence_type,
                description=description,
                artifact=artifact,
            )
        except Exception:
            pass
    # Fallback: attempt minimal close if cid appears open
    try:
        om = open_map
        if om is None:
            evs = list(events) if events is not None else eventlog.read_all()
            om = _idx.build_open_index(evs)
        if cid not in om:
            return False
        meta = {
            "cid": str(cid),
            "evidence_type": str(evidence_type),
            "description": str(description),
            "clean": True,
        }
        if artifact is not None:
            meta["artifact"] = str(artifact)
        eventlog.append(
            kind="commitment_close", content=f"Commitment closed: {cid}", meta=meta
        )
        return True
    except Exception:
        return False


def expire_commitment(
    eventlog: EventLog,
    *,
    cid: str,
    reason: str = "manual",
    at_iso: str | None = None,
    events: Iterable[dict] | None = None,
    open_map: dict[str, dict] | None = None,
    text0: str | None = None,
) -> bool:
    """Append a commitment_expire event for an open cid (idempotent-ish).

    Validates that the cid is currently open. Returns True on emit, False if
    cid not open or on failure.
    """
    try:
        om = open_map
        if om is None:
            evs = list(events) if events is not None else eventlog.read_all()
            om = _idx.build_open_index(evs)
        if cid not in om:
            return False
        if text0 is None:
            text0 = str((om.get(cid) or {}).get("text") or "")
        meta = {"cid": str(cid), "reason": str(reason)}
        if at_iso is not None:
            meta["expired_at"] = str(at_iso)
        eventlog.append(
            kind="commitment_expire",
            content=f"Commitment expired: {text0}",
            meta=meta,
        )
        return True
    except Exception:
        return False


def snooze_commitment(
    eventlog: EventLog,
    *,
    cid: str,
    until_tick: int,
) -> bool:
    """Append a commitment_snooze event; no-op if not an improvement.

    Emits only when the requested until_tick is greater than any existing
    snooze for the cid to preserve idempotency and monotonicity.
    """
    try:
        snoozed = _idx.build_snooze_index(eventlog.read_all())
        current = int(snoozed.get(cid, 0))
        new_until = int(until_tick)
        if new_until <= current:
            return False
        eventlog.append(
            kind="commitment_snooze",
            content="",
            meta={"cid": str(cid), "until_tick": new_until},
        )
        return True
    except Exception:
        return False


def rebind_commitment(
    eventlog: EventLog,
    *,
    cid: str,
    old_name: str,
    new_name: str,
    identity_adopt_event_id: int | None = None,
    original_text: str | None = None,
) -> bool:
    """Append a commitment_rebind marker with standard meta fields.

    This does not modify the underlying text; higher-level flows may emit a
    subsequent commitment_update as in legacy tracker behavior.
    """
    try:
        meta = {
            "cid": str(cid),
            "old_name": str(old_name),
            "new_name": str(new_name),
        }
        if identity_adopt_event_id is not None:
            meta["identity_adopt_event_id"] = int(identity_adopt_event_id)
        if original_text is not None:
            meta["original_text"] = str(original_text)
        eventlog.append(kind="commitment_rebind", content="", meta=meta)
        return True
    except Exception:
        return False


__all__.extend(
    [
        "add_commitment",
        "close_commitment",
        "expire_commitment",
        "snooze_commitment",
        "rebind_commitment",
    ]
)
