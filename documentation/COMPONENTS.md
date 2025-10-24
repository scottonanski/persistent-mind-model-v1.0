# Components Map

A pragmatic map of core modules with purpose, main responsibilities, and entry points for extension. File references include starting line for quick navigation.

## Storage

- EventLog — `pmm/storage/eventlog.py:1`
  - Hash-chained, append-only ledger with tail cache, read helpers, and optional embeddings side table.
- Projection — `pmm/storage/projection.py:1`
  - Replays events into identity + commitments. Enforces bounded trait deltas; provides directive views.
- Snapshot — `pmm/storage/snapshot.py:1`
  - Compressed, versioned projection snapshots; delta replay; integrity verification.
- Semantic Search — `pmm/storage/semantic.py:1`
  - Brute-force cosine over embedding blobs; used by recall and analysis.

## Runtime (Core)

- Context Builder — `pmm/runtime/context_builder.py:1`
  - Deterministic prompt assembly from ledger, with compact and standard formats.
- Generation Controller — `pmm/runtime/generation_controller.py:1`
  - Token budgeting, continuation strategy, telemetry logging.
- NLG Guards — `pmm/runtime/nlg_guards.py:1`
  - Rewrites capability claims; removes speculative event IDs.
- Validators — `pmm/runtime/validators.py:1`
  - Deterministic format checks for probes and gate checks; metric claim validation.
- Invariants — `pmm/runtime/invariants.py:1`
  - Ledger, identity, commitment, embedding, insight, scene compact, and bandit invariants.
- Fact Bridge — `pmm/runtime/fact_bridge.py:1`
  - Authoritative, read-only answers for event count, stage, and open commitments.

## Runtime (Cognition & Evolution)

- Reflector — `pmm/runtime/reflector.py:1`
  - Hygiene, novelty and bootstrap gating for reflections.
- Meta Reflection — `pmm/runtime/meta/meta_reflection.py:1`
  - Embedding-based scoring for depth, follow-through, evolution; anomaly detection.
- Metrics — `pmm/runtime/metrics.py:1`
  - IAS/GAS computation with tick-based windows, decay, and feedback coupling.
- Stage Tracker — `pmm/runtime/stage_tracker.py:1`
  - Stage inference and policy hints with hysteresis.
- Evolution Kernel — `pmm/runtime/evolution_kernel.py:1`
  - Proposes trait adjustments based on commitment outcomes and metrics; triggers reflections.

## Commitments

- Tracker — `pmm/commitments/tracker.py:1`
  - Lifecycle, evidence handling, project grouping, and dedupe/structure checks.
- Extractor — `pmm/commitments/extractor.py:1`
  - Semantic extraction of commitments from assistant text.
- Restructuring — `pmm/commitments/restructuring.py:1`
  - Normalizes and rebases commitments under identity changes.

## API & UI

- Companion API — `pmm/api/companion.py:1`
  - FastAPI endpoints for snapshot, metrics, chat, reflections, commitments, traces.
- UI — `ui/`
  - Next.js 15 application providing chat and observability dashboards.

## Where To Extend

- New event kinds: extend invariants and projections; add tests under `tests/`.
- New provider: implement `ChatAdapter` and register in `pmm/llm/factory.py`.
- New metric: append `metrics_update` events; surface via `companion.py`.
- New guard: add to `nlg_guards.py` or `validators.py` and wire into the loop.

