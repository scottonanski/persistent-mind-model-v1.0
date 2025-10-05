# Commitments Tracker API (v1)

This API provides read helpers (pure) and write helpers (delegating to legacy tracker when available) to standardize commitment lifecycle operations.

## Read Helpers (Pure)
- `snapshot(events) -> Store`
- `open_commitments(events) -> Dict[cid, meta]`
- `snoozed_until_tick(events) -> Dict[cid, until_tick]`
- `expired_by_hours(events, ttl_hours, now_iso=None) -> List[(cid, -1)]`
- `due_now(events, horizon_hours, now_epoch) -> List[(cid, due_epoch)]`
- Windowed queries: `open_effective_at`, `opens_within`, `closes_within`, `expires_within`
- Filtered views: `open_by_reason(events, reason)`, `open_by_stage(events, stage)`

All read helpers are deterministic: no side effects, no env gates.

## Write Helpers (Facade)
- `add_commitment(eventlog, text, source=None, extra_meta=None, project=None) -> str`
  - Emits `commitment_open` after structural validation/dedup (via legacy tracker when possible).
- `close_commitment(eventlog, cid, evidence_type='done', description='', artifact=None) -> bool`
  - Closes only if open; text-only evidence allowed unless configured otherwise.
- `expire_commitment(eventlog, cid, reason='manual', at_iso=None) -> bool`
  - Emits `commitment_expire` only if currently open.
- `snooze_commitment(eventlog, cid, until_tick) -> bool`
  - Emits `commitment_snooze` only when `until_tick` increases (monotonic/idempotent).
- `rebind_commitment(eventlog, cid, old_name, new_name, identity_adopt_event_id=None, original_text=None) -> bool`
  - Emits `commitment_rebind` marker for identity transitions.

Write helpers delegate to the legacy `CommitmentTracker` when available to preserve idempotency and behavior. Fallbacks perform minimal deterministic emissions.

## Notes
- Selective routing: Reads prefer store/indexes with projection fallback.
- Backward compatibility: `pmm.commitments.__init__` re-exports `CommitmentTracker` and `Commitment` (from `types`).
- Replay semantics and invariants: see `docs/commitments/tracker-invariants.md`.
