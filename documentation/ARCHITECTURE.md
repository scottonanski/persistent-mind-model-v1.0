# Architecture Overview

PMM is an event‑sourced cognitive system. Identity, traits, commitments, reflections, metrics, and stage are all derived by replaying an append‑only ledger. A small runtime coordinates prompting, validation, and persistence so identity persists across sessions and even model providers.

## Top‑Level Flow

1) Ledger → Snapshot/Projections → Prompt Context
2) LLM Generation → Post‑guards → Ledger Append
3) Autonomy Loop → Metrics/Policies/Reflections → Ledger
4) Companion API/UI → Read‑only introspection

```
User Or Tick
   │
   ▼
Context Builder (ledger slice)  pmm/runtime/context_builder.py:1
   │
   ▼
LLM Adapter (OpenAI/Ollama)     pmm/llm/factory.py:1
   │
   ▼
NLG Guards + Validators         pmm/runtime/nlg_guards.py:1, pmm/runtime/validators.py:1
   │
   ▼
EventLog.append (hash‑chained)  pmm/storage/eventlog.py:1
   │
   ├─► Projections/Snapshots     pmm/storage/projection.py:1, pmm/storage/snapshot.py:1
   └─► Autonomy/Policies         pmm/runtime/loop.py:1
          ├─ Metrics (IAS/GAS)   pmm/runtime/metrics.py:1
          ├─ Stage Tracker       pmm/runtime/stage_tracker.py:1
          ├─ Reflections         pmm/runtime/reflector.py:1, pmm/runtime/meta/meta_reflection.py:1
          └─ Commitments         pmm/commitments/tracker.py:1
```

## Key Principles

- Truth‑first: Everything derives from the ledger; the runtime does not “remember” outside it.
- Deterministic: Same ledger → same identity and state. Hash chaining enables audit.
- Read‑mostly: Builders and probes never mutate; only explicit append points write.
- Provider‑agnostic: Adapters implement a minimal `ChatAdapter` interface.

## Core Subsystems

- Ledger Storage
  - SQLite `EventLog` with prev_hash/hash for integrity; tail caching for speed.
  - Optional `event_embeddings` side‑table for semantic recall.
- Projection + Snapshot
  - `build_self_model` folds events into identity + commitments view.
  - `projection_snapshot` events anchor compressed state to accelerate rebuilds.
- Runtime Pipeline
  - Context assembly, guardrails, validation, append, and background autonomy.
  - Reflection gating, metrics recompute, stage inference with hysteresis.
- Commitments
  - Extraction from assistant text, lifecycle events, evidence, project grouping.
- Observability
  - FastAPI Companion exposes snapshots, metrics, events, and streaming chat.

## Event Kinds (selected)

- Identity: `identity_adopt`, `identity_change`, `identity_clear`
- Traits: `trait_update`
- Cognition: `reflection`, `meta_reflection`, `insight_ready`
- Commitments: `commitment_open`, `commitment_close`, `commitment_expire`, `commitment_update`, `commitment_rebind`, `project_open`, `project_assign`, `project_close`, `evidence_candidate`
- Autonomy/Policy: `autonomy_tick`, `policy_update`, `stage_update`, `stage_progress`, `metrics_update`, `gas_breakdown`
- Storage/Infra: `projection_snapshot`, `embedding_indexed`, `embedding_skipped`, `scene_compact`, `invariant_violation`

See `documentation/LEDGER.md` for schema and invariants.

