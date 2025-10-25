# Claims → Evidence Matrix

This matrix maps key philosophical claims to concrete evidence in the codebase and ledger, plus quick ways to observe them.

## C1. Identity exists “now” and is reconstructible
- Mechanism: build_identity from event replay
  - pmm/storage/projection.py:196
- Inputs: identity_adopt, identity_change, identity_clear, trait_update
- Observe:
  - API: GET /snapshot → identity
  - Code: pmm/runtime/context_builder.py:1
- Tests (representative): tests/test_invariants_identity.py

## C2. The system knows where it is relative to its history
- Mechanisms:
  - StageTracker.infer_stage over IAS/GAS telemetry
    - pmm/runtime/stage_tracker.py:1
  - get_or_compute_ias_gas (decay, stability windows, feedback loop)
    - pmm/runtime/metrics.py:1
- Observe:
  - API: GET /metrics?detailed=true
  - Events: autonomy_tick (with telemetry)

## C3. It can shape who it will become via commitments
- Mechanisms:
  - Commitment lifecycle with evidence gating
    - pmm/commitments/tracker.py:1, pmm/runtime/invariants.py:1
  - GAS growth from clean closes and novelty
    - pmm/runtime/metrics.py:1
- Observe:
  - API: GET /commitments?status=open; GET /reflections
  - Events: commitment_open, evidence_candidate, commitment_close

## C4. Identity persists across model swaps (LLM-agnostic)
- Mechanisms:
  - Ledger-derived identity; adapters don’t alter projection semantics
    - pmm/runtime/context_builder.py:1, pmm/storage/projection.py:1
    - LLMFactory configuration only: pmm/llm/factory.py:1
- Observe:
  - Run same ledger with different adapters; compare GET /snapshot and /metrics

## C5. The ledger is auditable (append-only, verifiable)
- Mechanisms:
  - SHA-256 hash chaining; verify_chain()
    - pmm/storage/eventlog.py:421
- Observe:
  - Call EventLog.verify_chain()
  - Invariants runtime: pmm/runtime/invariants_rt.py:1

## C6. Reflection is filtered for hygiene and novelty; deeper analysis is semantic
- Mechanisms:
  - Reflection accept gate (length, n-gram dedup, policy-loop guard)
    - pmm/runtime/reflector.py:1
  - Meta reflection scores depth/evolution/follow-through via embeddings
    - pmm/runtime/meta/meta_reflection.py:1
- Observe:
  - API: GET /reflections
  - Meta reports: meta_reflection_report events

## C7. Snapshots reproduce projection; deltas are applied
- Mechanisms:
  - projection_snapshot pointer; compressed state storage, checksum
    - pmm/storage/snapshot.py:240
- Observe:
  - Verify integrity at anchors; rebuild on mismatch
  - Faster rebuilds with delta replay

