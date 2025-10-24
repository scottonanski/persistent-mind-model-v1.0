# Core Concepts

This project is a systematic inquiry into whether identity can be established and evolved through layers of abstraction across time, using a self-referential, append-only ledger. PMM operationalizes this as deterministic data structures and flows.

## Identity Inquiry (Research Questions)

- Can a system locate “who it is now” from its history alone?
  - Signals: last `identity_adopt`, accumulated trait state, recent reflections mentioning identity.
  - Evidence: projection output (`build_identity`), context builder state, IAS stability.

- Can it trace how it became this identity (provenance)?
  - Signals: sequence of identity events; meta-reflection narratives; stage progression.
  - Evidence: append-only ledger replay; `meta_reflection_report` summaries; `stage_progress`.

- Can it commit to future actions that shape who it will become?
  - Signals: `commitment_open` with project tags; `evidence_candidate` and `commitment_close`.
  - Evidence: GAS growth from clean closes; project lifecycle events; policy updates.

- Can it self-regulate identity drift based on outcomes?
  - Signals: `trait_update` deltas gated by invariants; evolution kernel proposals.
  - Evidence: IAS stability bonuses and flip-flop penalties; stage hysteresis; drift rate limits.

- Does identity persist across model swaps (provider-agnostic)?
  - Signals: consistent projection after adapter/model change.
  - Evidence: same ledger → same identity and traits; reproducible IAS/GAS paths.

## Identity

- Defined by ledger events, not by model memory.
- Current identity = last adoption plus trait state from projection.
- Files: `pmm/storage/projection.py:1`, `pmm/runtime/context_builder.py:1`

## Traits (OCEAN)

- Numeric in [0,1] for openness, conscientiousness, extraversion, agreeableness, neuroticism.
- Drift via `trait_update` events with per-event clamp; strict invariants optionally enforced.
- Files: `pmm/storage/projection.py:132`, `pmm/runtime/invariants.py:1`

## Commitments

- Ground truth for intention and follow-through.
- Lifecycle: open → evidence_candidate(s) → close/expire; optional projects group related commitments.
- Evidence gates ensure closes are justified; validators prevent structural errors and duplicates.
- Files: `pmm/commitments/tracker.py:1`, `pmm/runtime/invariants.py:1`

## Reflections

- Self-referential narrative that can propose adjustments and generate commitments.
- Acceptance gate enforces hygiene and novelty before admitting reflections to the ledger.
- Meta-reflection scores depth, follow-through, and evolution via embeddings.
- Files: `pmm/runtime/reflector.py:1`, `pmm/runtime/meta/meta_reflection.py:1`

## Metrics (IAS/GAS)

- IAS: identity stability over time (stability bonuses, flip-flop penalties, decay).
- GAS: growth from commitments (novel opens, clean closes) with gentle feedback coupling to IAS.
- Files: `pmm/runtime/metrics.py:1`, `pmm/runtime/stage_tracker.py:1`

How they answer the inquiry:
- IAS quantifies identity persistence; stability windows accumulate as the system holds to an adopted name without flip-flopping.
- GAS quantifies growth through honored commitments; clean closes increase GAS; novelty and projects show directed development.

## Stage (S0→S4)

- Stage is inferred from recent IAS/GAS windows with hysteresis and emits policy hints.
- Files: `pmm/runtime/stage_tracker.py:1`

## Append-Only Auditability

- Every event carries a chain hash; `verify_chain()` recomputes the entire chain.
- Snapshots compress projection state at deterministic anchors; integrity is verifiable.
- Files: `pmm/storage/eventlog.py:1`, `pmm/storage/snapshot.py:1`

## Provider-Agnostic Identity

- The LLM changes, the ledger does not. Replaying the ledger through adapters yields the same identity and behavior envelope.
- Files: `pmm/llm/factory.py:1`, `pmm/runtime/context_builder.py:1`
