# Ledger and Projections

PMM’s mind is an append-only SQLite ledger with SHA-256 hash chaining for integrity. All higher-level state (identity, traits, commitments, metrics, stage) is reconstructed by deterministic projection.

## EventLog

- Storage: `pmm/storage/eventlog.py:1`
- Columns: `id`, `ts`, `kind`, `content`, `meta`, plus `prev_hash`, `hash` for tamper evidence.
- API:
  - `append(kind, content, meta) -> id`
  - `read_all() -> list[dict]`, `read_tail(limit)`, `read_after_id(after_id, limit)`
  - `verify_chain() -> bool` to recompute the hash chain
- Optimizations: tail cache, read-after, partial indexes, optional `event_embeddings` side table for semantic search (`pmm/storage/semantic.py:1`).

## Projections

- `build_self_model(events)` → identity + commitments view (`pmm/storage/projection.py:1`)
  - Identity: name and OCEAN traits with clamped deltas; supports legacy single-trait and multi-delta schema.
  - Commitments: open/expired maps keyed by `cid`, updated by lifecycle events.
- `build_identity(events)` → identity only (stable ordering of trait keys).
- Determinism: given the same ordered events, output is byte-for-byte stable.

## Snapshots

- Purpose: accelerate rebuilds by storing compressed projection state at fixed event anchors.
- Impl: `projection_snapshot` pointer events + `snapshots` table (`pmm/storage/snapshot.py:1`).
- Contract: snapshots are reproducible from events; checksum verified; schema-versioned.
- Usage: `build_self_model_optimized(events, eventlog=...)` applies delta over latest snapshot.

## Event Schema and Kinds (representative)

- Common fields per event: `{id:int, ts:str, kind:str, content:str, meta:dict}`
- Identity
  - `identity_adopt`: meta `{name, sanitized?, confidence?}`
  - `identity_change`, `identity_clear`
- Traits
  - `trait_update`: meta `{trait?, delta} or {delta:{o,c,e,a,n}}` (clamped)
- Commitments
  - `commitment_open`: meta `{cid, text, source?, project_id?}`
  - `commitment_update`: meta `{cid, old_text, reason}`
  - `commitment_close`: meta `{cid, evidence_type:"done", description, artifact?, project_id?}`
  - `commitment_expire`, `commitment_snooze`
  - Evidence support: `evidence_candidate`: meta `{cid, evidence_type, snippet}`
  - Projects: `project_open|assign|close` with `project_id`
- Cognition
  - `reflection` (free text with acceptance gate), `meta_reflection_report`
  - `insight_ready`: points at a `reflection` via `meta.from_event`
- Autonomy/Policy
  - `autonomy_tick`: `meta.telemetry = {IAS, GAS}`
  - `stage_update` / `stage_progress` for stage awareness
  - `metrics_update`, `gas_breakdown` for IAS/GAS records
  - `policy_update` per component (reflection cadence, drift parameters)
- Infra
  - `projection_snapshot`, `embedding_indexed|skipped`, `scene_compact`, `invariant_violation`

## Invariants (selected)

- Ledger shape: monotonically increasing ids; `kind` is string; `meta` is dict (`pmm/runtime/invariants.py:1`).
- Identity: name sanitization; adopt→response ordering hints; proposal/adopt pacing.
- Commitments: close requires prior `evidence_candidate` after the open; adjacent duplicate evidence blocked; TTL/expire must reference open.
- Insight: `insight_ready` references a prior reflection and is consumed once.
- Embeddings: `embedding_indexed` points to prior event and carries a non-duplicate digest.
- Scene compaction: `source_ids` are prior, strictly increasing, match declared window.

Violations are detected and (optionally) recorded as `invariant_violation` events.

