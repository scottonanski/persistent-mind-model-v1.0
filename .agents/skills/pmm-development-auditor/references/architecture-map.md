# PMM Architecture Map

This is a navigation aid, not proof of current behavior. Re-read the current symbols and their callers before reporting a guarantee. Prefer `rg` searches for symbol and event-kind names over stored line numbers.

## Canonical audit surfaces

| Concern | Primary symbols and files | Questions to trace |
|---|---|---|
| Event preservation and chaining | `EventLog.append`, `EventLog.append_terminal_outcome` in `pmm/core/event_log.py` | What is written, deduplicated, rejected, or linked? Which paths bypass normal append logic? |
| Claim extraction | `extract_claims` in `pmm/core/semantic_extractor.py`; claim handling in `PMMLoop.run_turn` in `pmm/runtime/loop.py` | Which utterances become claim candidates? What survives malformed or rejected input? |
| Claim and evidence validation | `validate_claim_detailed`, `validate_evidence_designations` in `pmm/core/validators.py` | Which fields are optional? Which targets, roles, kinds, and retrieval constraints are checked? What is the unknown-type policy? |
| Identity adoption | `maybe_append_identity_adoptions` in `pmm/core/identity_manager.py` | How are proposal, anchor, ratification, and adoption connected? Is ordering confused with relevance? |
| Commitment lifecycle | `CommitmentManager` in `pmm/core/commitment_manager.py`; commitment handling in `pmm/runtime/loop.py` | How are CIDs created, opened, closed, projected, and linked to producing events? |
| Fast state projection | `Mirror` in `pmm/core/mirror.py` | Which event kinds mutate projected state? Can replay and incremental sync diverge? |
| Recursive self-model | `RecursiveSelfModel` in `pmm/core/rsm.py` | Which self-descriptions are computed signals, lexical proxies, or semantic interpretations? |
| Causal and thread topology | `MemeGraph._add_event`, `thread_for_cid`, `cids_for_event` in `pmm/core/meme_graph.py` | Which edges are explicit, inferred, optional, or silently absent? Are targets validated? |
| Concept topology | `ConceptGraph` in `pmm/core/concept_graph.py`; schemas in `pmm/core/concept_schemas.py`; `ConceptOpsCompiler` in `pmm/core/concept_ops_compiler.py` | How are definitions, aliases, relations, event bindings, thread bindings, versions, and supersessions produced and checked? |
| Binding provenance | `binding_attribution_meta` and related validation in `pmm/core/binding_attribution.py` | Does a binding merely exist, or is its author and origin established? |
| Retrieval | `run_retrieval_pipeline` in `pmm/retrieval/pipeline.py`; rendering in `pmm/runtime/context_renderer.py` | Which events were eligible, selected, forced, expanded, or omitted? Is provenance retained? |
| Reflection | `synthesize_reflection` in `pmm/runtime/reflection_synthesizer.py`; turn-delta reflection in `pmm/runtime/loop.py`; edges in `MemeGraph` | Do all reflection producers identify their referents consistently? What consumes those links? |
| Long-range compression | `maybe_append_lifetime_memory` in `pmm/runtime/lifetime_memory.py` | Which source handles survive compression, and can retrieval reopen them? |
| Autonomous maintenance | `AutonomyKernel` in `pmm/runtime/autonomy_kernel.py` | Which decisions are computed, which write state, and which rely on graph or projection assumptions? |

## Lifecycle tracing pattern

For an event or field, search in this order:

```text
schema or parser
  -> all producers
  -> validation call sites
  -> append or rejection behavior
  -> listeners and projections
  -> retrieval and rendering
  -> promotion or state mutation
  -> tests and exported runtime evidence
```

Search both the symbol and its serialized names. For example, a complete reference audit normally searches the Python field name, JSON key, event kind, validator, and projection consumer.

## Current high-value audit anchors

Re-verify these in current code; they are starting hypotheses, not permanent facts:

- Evidence-reference validation may be conditional on the field being declared.
- Different reference-bearing structures may receive different levels of target validation.
- Identity adoption may establish temporal ordering without establishing identity relevance.
- Reflection producers may not populate relational metadata uniformly.
- Concept supersession may have schema checks that are weaker than ledger-aware relationship checks.
- Invalid model output may remain in historical form even when canonical promotion is rejected.
- Unknown structured types may have a different policy from registered types.

If any hypothesis is no longer true, report the current code and update this reference only when the user asks to maintain the skill.
