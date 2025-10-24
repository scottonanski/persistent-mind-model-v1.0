# Runtime Pipeline

The runtime coordinates prompt assembly, generation, validation, and append. It also runs a background autonomy loop that maintains metrics, reflections, and policy-driven behavior.

## Context Assembly

- Module: `pmm/runtime/context_builder.py:1`
- Builds a deterministic system prompt from the ledger:
  - Identity (name, OCEAN traits) with stable ordering
  - User identity if present
  - IAS/GAS and stage (via `StageTracker` and metrics)
  - Open commitments (grounded by actual event ids)
  - Recent reflections (compact, budgeted)
  - Optional MemeGraph summary
- Tail optimization with controlled fallback to full scan; accepts optional `LedgerSnapshot`.

## Generation Control

- Module: `pmm/runtime/generation_controller.py:1`
- Budgets tokens based on model caps and task, supports continuation on `stop_reason=length`.
- Records allocation telemetry via `pmm/runtime/alloc_log.py`.

## Post-Guards and Validators

- Capability claims guard: `pmm/runtime/nlg_guards.py:1`
  - Rewrites impossible claims (e.g., “I can create events”) to ledger-truth phrasing.
  - Removes speculative future event ids when not confirmed.
- Output validators: `pmm/runtime/validators.py:1`
  - Probe and gate-check format validators, metric claim checks, language sanitation.
- Fact bridge: `pmm/runtime/fact_bridge.py:1` provides authoritative counts (events, open commitments, stage).

## Autonomy Loop

- Entry: `pmm/runtime/loop.py:1` (facade)
- Responsibilities:
  - Reflection cadence and acceptance (see `pmm/runtime/reflector.py:1`)
  - Commitment extraction and lifecycle (`pmm/commitments/tracker.py:1`)
  - Metrics recomputation and `autonomy_tick` emission (`pmm/runtime/metrics.py:1`)
  - Stage inference and policy hints (`pmm/runtime/stage_tracker.py:1`)
  - Bandit guidance, recall suggestions, planning hooks

## Metrics and Stage

- IAS/GAS computation: `pmm/runtime/metrics.py:1`
  - Tick-based windows; identity flip-flop penalties; stability bonuses; gentle decay
  - Feedback loop between IAS and GAS
  - Writes `metrics_update` events; `get_or_compute_ias_gas` hybrid path with DB read + recompute
- Stage inference: `pmm/runtime/stage_tracker.py:1`
  - Rolling window across `autonomy_tick` (and supplemental reflection telemetry)
  - Hysteresis for up/down transitions and policy hints per stage

## Snapshots

- `pmm/storage/snapshot.py:1` stores compressed projection state and emits `projection_snapshot` events.
- `build_self_model_optimized` restores snapshot then replays deltas; optional integrity verification.

## MemeGraph (optional)

- `pmm/runtime/memegraph.py:1` provides a graph view over events for richer identity/stage summaries.
- Context builder can prioritize MemeGraph for stage and identity provenance when present.

## API and UI

- Companion API: `pmm/api/companion.py:1` exposes snapshot, metrics, chat, reflections, commitments.
- UI: Next.js app under `ui/` renders chat, ledger, metrics, traces, and identity views.

