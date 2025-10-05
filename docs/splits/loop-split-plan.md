# PMM Runtime Loop Split Plan

Owner: Runtime/Core
Scope: `pmm/runtime/loop.py`
Status: Proposed

## Executive Summary

`pmm/runtime/loop.py` (~7,000+ LOC) centralizes tick orchestration, pipeline stages, metrics, tracing, and service wiring. The module’s size and responsibility breadth increase coupling and cognitive load. This plan splits the loop into cohesive, testable components behind a stable public façade to preserve behavior while improving maintainability and reliability.

## Goals

- Reduce module size and responsibility overlap; isolate async scheduling from business logic.
- Maintain deterministic replay and event emission semantics.
- Keep public entrypoints stable for CLI/UI integration during the migration.
- Improve testability and enable targeted performance work.

## Non-Goals

- Redesigning pipeline semantics or reflection logic.
- Changing external protocols or UI trace payload shapes.

## Current Responsibilities (to be separated)

- Tick orchestration, backpressure, cancellation, and lifecycle control.
- Stage pipeline execution (classify → reflect → commit → emit).
- Commitments: due evaluation and interactions with tracker.
- State access: eventlog, snapshot, projection cache.
- Streaming traces to UI and metrics collection/reporting.
- LLM bridge and adapter orchestration.
- Configuration, invariants, and guardrails.

## Target Architecture (new package)

New package: `pmm/runtime/loop/`

- `api.py`
  - Stable public entrypoints (e.g., `run()`, `shutdown()`).
  - Backward-compatible façade initially re-exported from `pmm/runtime/loop.py`.
- `scheduler.py`
  - Tick control: cadence, jitter, backpressure thresholding, cancellation.
  - Owns asyncio constructs and lifecycle signals.
- `pipeline.py`
  - Ordered stage execution with pure(ish) handlers; idempotent emit-on-replay.
  - Clear error boundaries; structured results for metrics/tracing hooks.
- `io.py`
  - Trace emitters and adapters (to `trace_buffer`, websockets, files).
  - Metrics hook points (counters/timers) delegated to `pmm/runtime/metrics.py`.
- `services.py`
  - Typed dependency container (eventlog, snapshot, projection cache, metrics, bridge, tracker).
  - Prevent circular imports via explicit wiring.

Key integrations remain unchanged:

- Metrics: `pmm/runtime/metrics.py`
- Traces: `pmm/runtime/trace_buffer.py`
- State: `pmm/storage/eventlog.py`, `pmm/storage/snapshot.py`, `pmm/storage/projection_cache.py`
- Bridge: `pmm/bridge/manager.py`, `pmm/runtime/bridge.py`
- Commitments: `pmm/commitments/tracker.py`

## Migration Plan (4 stages)

Stage 1 — Bootstrap (no behavior change)

- Create `pmm/runtime/loop/` with `api.py` containing types/constants and thin wrappers.
- Keep `pmm/runtime/loop.py` as façade re-exporting `loop.api` functions.
- Add smoke import test (import-time only) to ensure no cycles.

Stage 2 — Extract IO + Metrics

- Move trace streaming and metric-counter code into `io.py` and hook functions.
- Replace inline metrics with `metrics.*` calls behind `io` hooks.
- Validate via `tests/test_streaming.py` and UI manual smoke (unchanged payloads).

Stage 3 — Extract Scheduler

- Move tick cadence/jitter/backpressure/cancellation into `scheduler.py`.
- Confine asyncio primitives (tasks, events) to scheduler; pipeline exposed as sync/awaitable callable.
- Validate with `tests/test_reflection_runtime.py`, `tests/test_stage_behavior_manager.py`.

Stage 4 — Extract Pipeline

- Move stage handlers into `pipeline.py` with explicit inputs/outputs.
- All state access goes through `services.py`; no direct imports from storage modules.
- Ensure idempotent replay and no double emits.
- Validate with reflection- and bandit-related tests.

## Acceptance Criteria

- All tests pass with no skips: `tests/test_streaming.py`, `tests/test_reflection_runtime.py`, `tests/test_stage_behavior_manager.py`, `tests/test_reflection_bandit.py`, `tests/test_trait_nudges.py`.
- Public entrypoints used by `pmm/cli/chat.py` remain stable; UI trace events unchanged.
- No circular imports introduced; clean shutdown works under load.
- Deterministic event replay; no duplicate event emissions across replays.

## Invariants and Guardrails

- Replay determinism: same inputs → same stage outputs and event emissions.
- Backpressure capped: scheduler must not accumulate unbounded work.
- Trace buffer integrity: ordering preserved, bounded memory usage.

## Risks and Mitigations

- Hidden cross-cutting side effects
  - Mitigate by extracting IO/metrics first to surface dependencies.
- Async bugs and cancellation races
  - Confine asyncio to `scheduler.py` and keep stage logic pure-ish.
- Import cycles during extraction
  - Use `services.py` for explicit wiring; avoid deep imports across layers.

## Test & Validation Plan

- Unit/regression: run existing tests covering streaming, reflection, stage behavior, and bandit logic.
- Determinism: re-run `tests/test_snapshot_determinism.py` and `tests/test_snapshot_memegraph.py` as sanity.
- Perf smoke: `scripts/phase3_stage2_benchmark.py` before/after to ensure no regressions.

## Effort and Rollback

- Effort: ~2–3 dev-days including CI stabilization.
- Rollback: keep the old façade until final extraction; revert by pointing façade back to pre-split implementations.

## Work Breakdown (checklist)

- [ ] Add `loop/` package with `api.py`, `services.py` scaffolding
- [ ] Move trace emission + metrics hooks to `io.py`
- [ ] Extract `scheduler.py` and route all tick control through it
- [ ] Extract `pipeline.py` stage handlers and wire to `services.py`
- [ ] Remove dead code and deprecated paths in `loop.py`; keep shims
- [ ] Update module docs and developer notes

