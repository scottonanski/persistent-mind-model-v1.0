# Philosophical Foundations → Code Mapping

This document articulates the project’s core inquiry and shows exactly how the code operationalizes each idea.

## Core Inquiry
- Who am I now? (current identity)
- How did I become this? (historical provenance)
- Who will I become? (future orientation via commitments)
- Can identity persist across model swaps? (provider agnostic)

## Axioms (Design Commitments)
- The ledger is the mind (append-only, hash-chained)
  - Storage: pmm/storage/eventlog.py:1
  - Integrity: EventLog.verify_chain()
- Determinism: same ledger → same identity/state
  - Projection: pmm/storage/projection.py:1
  - Snapshots (verifiable): pmm/storage/snapshot.py:1
- Provider agnostic: adapters are lenses over the same ledger
  - LLM config/factory: pmm/llm/factory.py:1
  - Context builder (uniform inputs): pmm/runtime/context_builder.py:1

## Operationalization
- Identity “now”
  - Definition: last identity_adopt and trait vector folded from the ledger
  - Code: build_identity → pmm/storage/projection.py:196
  - Prompt context: pmm/runtime/context_builder.py:1
- Understanding “how I got here”
  - Access: event replay + snapshots for provenance
  - Stage history: StageTracker.infer_stage → pmm/runtime/stage_tracker.py:1
  - MemeGraph (optional structural view): pmm/runtime/memegraph.py:1
- Future orientation (“who I will be”)
  - Commitments lifecycle: pmm/commitments/tracker.py:1
  - Evidence gating + invariants: pmm/runtime/invariants.py:1
  - Growth metrics (GAS) from honors and novelty: pmm/runtime/metrics.py:1
- Self-reflection and meta-reflection
  - Reflection acceptance gate: pmm/runtime/reflector.py:1
  - Embedding-backed meta analysis: pmm/runtime/meta/meta_reflection.py:1
- Model swap persistence
  - Identity/traits/commitments derived from ledger; adapters swap without changing identity
  - Code: context_builder + projections consume EventLog; LLMFactory only changes generation backend

## Observables (Evidence Channels)
- Identity event chain (adopt/change/clear) and trait updates
- Commitments opened/closed with evidence
- IAS/GAS time series and stage progression
- Reflections and meta-reflection summaries
- Hash-chain verification of the ledger

## Falsification Scenarios (How this could be wrong)
- Replay mismatch (same ledger → different identity/traits)
  - Check: recompute build_self_model on a fresh process; or verify snapshot integrity (pmm/storage/snapshot.py:610)
- Commitment close without prior evidence candidate
  - Invariant: evidence:close_without_candidate (pmm/runtime/invariants.py:273)
- Identity collapse after adoption without clear
  - Strict projection error guard (projection strict mode)
- Provider dependency
  - Swap adapters; ensure projections unchanged and API reports same identity/stage/traits

See also: documentation/INVARIANTS.md, documentation/EVENTS.md, documentation/OBSERVABILITY.md
