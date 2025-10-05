# Commitments Tracker Split Plan

Owner: Commitments/Core
Scope: `pmm/commitments/tracker.py`
Status: Proposed

## Executive Summary

`pmm/commitments/tracker.py` (~1,200+ LOC) aggregates data modeling, lifecycle/TTL logic, indexing, validation, and persistence. This plan separates concerns into a typed model layer, TTL/due scheduling components, storage/index modules, and a stable API façade. The split improves replay determinism, testability, and performance clarity without changing external semantics.

## Goals

- Clarify data models and CIDs; make invariants explicit and enforceable.
- Isolate TTL/due mechanisms for correctness under tick/replay.
- Separate persistence boundaries and derived indexes.
- Preserve existing APIs while migrating consumers incrementally.

## Non-Goals

- Redesigning commitment semantics or statuses.
- Changing event formats in the ledger.

## Current Responsibilities (to be separated)

- Commitment CRUD and status transitions.
- TTL and due scheduling; tick-driven expiry.
- Validation, invariants, and restructuring integration.
- Indexing and queries by status/priority/tags.
- Persistence/event emission via eventlog/projections.

## Target Architecture (new package)

New package: `pmm/commitments/tracker/`

- `types.py`
  - Typed models for commitments, statuses, and CID/hash utilities.
  - Serialization helpers used by ledger projections.
- `ttl.py`
  - TTL computation and tick-based expiry; idempotent under replay.
  - Boundary handling for off-by-one ticks and clock drift rules.
- `due.py`
  - Due-date calculation and scheduler hooks (integrates with runtime loop scheduler).
- `store.py`
  - Persistence boundaries and in-memory materialized view.
  - Interfaces with `pmm/storage/eventlog.py`, `pmm/storage/projection.py`, `pmm/storage/snapshot.py`.
- `indexes.py`
  - Derived and maintained indexes for fast lookups; recompute deterministically on replay.
- `api.py`
  - Stable high-level operations (add/update/complete/expire/reschedule) for consumers.
  - Delegates to `store`, `indexes`, `ttl`, and `due`.

Related integrations remain unchanged:

- Validation: `pmm/runtime/validators.py`
- Extraction: `pmm/commitments/extractor.py`
- Restructuring: `pmm/commitments/restructuring.py`
- State: `pmm/storage/eventlog.py`, `pmm/storage/projection.py`, `pmm/storage/snapshot.py`

## Migration Plan (5 steps)

Step 1 — Stabilize Types

- Extract data classes/enums and CID utilities to `types.py`.
- Add small unit tests focused on serialization/hash determinism only.

Step 2 — Extract TTL & Due

- Move TTL logic to `ttl.py` and due calculations to `due.py`.
- Keep old functions delegating to new modules; no behavior change.
- Validate with `tests/test_commitment_ttl_ticks.py`.

Step 3 — Extract Store & Indexes

- Create `store.py` to own persistence/materialized view boundaries.
- Move derived views into `indexes.py`; ensure recompute-from-ledger is idempotent.
- Validate replays with `tests/test_eventlog_coherence.py` and commitment tests.

Step 4 — Introduce API Façade

- Add `api.py` as the single import for other subsystems (loop, planning, prioritizer).
- Update internal imports to use `api.py`; keep shims in `tracker.py` for backwards compatibility.

Step 5 — Clean-up & Docs

- Remove dead code and deprecations in `tracker.py` once all consumers are migrated.
- Document invariants and replay behavior.

## Acceptance Criteria

- All tests pass with no skips: `tests/test_commitment_validator.py`, `tests/test_commitment_ttl_ticks.py`, `tests/test_reflection_commitments.py`, `tests/test_stage_tracker.py`.
- Deterministic behavior under event replay; consistent TTL/due outcomes.
- API surface documented and stable; types exported via `types.py`.

## Invariants and Guardrails

- CID determinism: models with equal input fields yield identical CIDs.
- TTL expiry occurs exactly at boundary ticks; no early/late transitions.
- Indexes match a full recompute from eventlog at any point in time.

## Risks and Mitigations

- Tight coupling with reflection/planning
  - Preserve old function entrypoints as shims while migrating to `api.py`.
- Persistence edge cases during replay
  - Encode invariants in tests; compare index snapshots before/after replays.
- Performance regressions in indexing
  - Keep index maintenance O(1)-amortized per event; microbench hot paths.

## Test & Validation Plan

- Unit: add narrow tests for `ttl.py` and `indexes.py` covering boundaries and idempotency.
- Regression: run existing validator and commitment tests; run eventlog coherence tests.
- Replay: re-materialize from eventlog and compare to live indexes.

## Effort and Rollback

- Effort: ~1.5–2 dev-days.
- Rollback: `tracker.py` delegates to old code paths; revert by rewiring shims.

## Work Breakdown (checklist)

- [ ] Extract and document `types.py` (CIDs, statuses)
- [ ] Move TTL logic to `ttl.py`; due logic to `due.py`
- [ ] Implement `store.py` and `indexes.py` with deterministic recompute
- [ ] Add `api.py`, migrate internal consumers incrementally
- [ ] Remove deprecated paths and update docs

