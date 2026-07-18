# Concept-authorship research stopping point

Current stopping point: `PMM-CONTROL` remains experimental. The candidate
parser's frozen-corpus safety and Gemma's accepted-definition quality are strong,
but requiring the conversational model to reproduce a managed `turn_ref` reduced
spontaneous appropriate authorship below the preregistered gate. Do not integrate
the channel into production yet.

Binding attribution was verified directly rather than inherited from earlier
commentary:

- `pmm/core/binding_attribution.py` landed in commit `950d00b`;
- `pmm/runtime/loop.py` calls `binding_attribution_meta` for active event indexing,
  commitment-thread bindings, and runtime claim projection;
- structured `concept_ops` bindings route through the same helper in
  `pmm/core/concept_ops_compiler.py`;
- `pmm/core/event_log.py` validates attribution metadata before appending binding
  events.

Next investigation: determine whether PMM can guarantee freshness without making
the conversational model carry the freshness mechanism. Compare, without assuming
a winner:

1. runtime-bound structured tool calls;
2. a schema-constrained second encoding pass;
3. direct activation with transactional current-turn binding;
4. quarantined provisional authorship.

Preserve the provider-neutral parser. Do not resume Granite primer iteration; its
mutation-judgment stopping rule fired decisively. Freeze evaluation criteria before
implementing or running another experiment. Capability attestation remains bounded
evidence under a frozen configuration, not a permanent guarantee of correct
judgment on unseen prompts.

The central open question is:

> Can PMM guarantee freshness without making the model serialize the freshness
> mechanism?

