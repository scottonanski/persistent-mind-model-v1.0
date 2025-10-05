# Tracker Invariants and Replay Semantics

This document captures the invariants, boundaries, and replay guarantees for the commitments tracker split.

## Core Invariants

- Determinism: All derived views depend only on the provided event list. No clocks, RNG, or env gates influence results.
- Idempotency: Recomputing indexes/store from the full ledger yields the same state. No in-place edits.
- Event ordering: Semantics assume `id` is a monotonically increasing surrogate for temporal order.
- Single-source-of-truth: The event log is authoritative; no shadow state stored elsewhere.

## Index Consistency

- Open set: A `commitment_open` remains open until a subsequent `commitment_close` or `commitment_expire` for the same `cid`.
- Close/Expire maps: Last-close/last-expire wins by ledger order (id asc).
- Snooze map: For each `cid`, the maximum `until_tick` is retained.
- Due emitted set: Tracks `commitment_due` by `cid` to avoid duplicates.

## TTL Boundaries

- Hours-based expiration: `expire_commitment` by hours uses event `ts` (ISO 8601). Age = `now_iso - open_ts`.
- Tick-based helpers: Auxiliary helpers rely on counting `autonomy_tick` events; callers keep tick semantics separate from hours TTL.
- Expire idempotency: `commitment_expire` is only emitted for `cid` currently in the open set at evaluation time.

## Replay Behavior

- Full replay: Rebuilding `Store` and indexes from `read_all()` must produce the same state as incremental maintenance.
- Windowed queries: Filtering by bounds (`since_id/until_id` and/or `since_ts/until_ts`) applies AND semantics when both dimensions provided.
- Monotonicity: `snooze_commitment` only emits when the requested `until_tick` exceeds any prior snooze for the same `cid`.
- Idempotent writes: Write helpers check open/closed state before emitting events to prevent duplicates on retries.

## Write API Guarantees (v1)

- `add_commitment`: Emits one `commitment_open`. Legacy behavior (dedup/structure) is preserved by delegating to the legacy tracker when possible.
- `close_commitment`: Emits `commitment_close` only if the `cid` is open. Text-only evidence allowed unless configured otherwise.
- `expire_commitment`: Emits `commitment_expire` only if the `cid` is open at evaluation time.
- `snooze_commitment`: Emits `commitment_snooze` only when the new `until_tick` is strictly greater than the current maximum.
- `rebind_commitment`: Emits `commitment_rebind` marker with optional `identity_adopt_event_id` and `original_text`.

## Operational Notes

- Selective routing: Read operations prefer store/indexes, with projection fallback for safety.
- Backward compatibility: Legacy `tracker.py` remains as a shim during migration.
- Testing: Integration tests validate write API idempotency and behavior; full test suite must remain green.

