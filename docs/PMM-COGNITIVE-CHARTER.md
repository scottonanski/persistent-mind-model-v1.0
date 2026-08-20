# PMM Cognitive Charter

## Purpose

Persistent Mind Model is not fundamentally a memory feature for agents. It is
an attempt to build reconstructable continuity: a durable structure through
which recorded experience can be remembered, interpreted, recursively
reinterpreted, and used to form and govern an evolving account of self.

PMM began with a thought experiment: if embodiment and immediate sensory
experience were stripped away, what could remain of a mind is a layered history
and the capacity to inspect it. Such a mind could reflect on memories, reflect
on earlier reflections, examine how and why those interpretations were formed,
and use their accumulated lineage to reach a present understanding of itself.
It could then make commitments to its future self and evaluate later experience
in relation to the identity and ontology it had formed.

PMM translates that originating idea into a software architecture. It preserves
recorded history, relationships, interpretations, commitments, and changes over
time without treating transient model state as durable authority.

Its governing architectural idea is:

> A self is an evolving network of remembered events, interpretations,
> relationships, and commitments that can reconstruct both its history and how
> that history acquired meaning.

This is a design commitment, not proof that a software system is conscious,
equivalent to a biological mind, or correct in its self-interpretation.

## Authority

The authority order for PMM development is:

1. This charter defines the intended cognitive architecture and its boundaries.
2. Current production code establishes what is implemented now.
3. Tests and runtime evidence corroborate the paths they actually exercise.
4. The System Guide describes the audited current implementation.
5. Research reports, transcripts, telemetry, and model interpretations are
   evidence or historical material, not governing specifications.

Current code does not silently redefine the intended architecture merely because
it already exists. The charter does not turn intended behavior into an
implemented guarantee merely by describing it.

The technical and architectural prose in `LICENSE.md` is part of the PMM-1.0
license and prior-art disclosure. It records historical design claims and legal
terms; it does not supersede this charter, current production code, or the
System Guide as a description of present implementation. This classification
does not alter the license terms.

## Cognitive lifecycle

PMM is directed toward a reconstructable lifecycle:

```text
experience
  -> interpretation
  -> interpretation of interpretation
  -> identity, ontology, or policy revision
  -> commitment
  -> outcome
  -> later reinterpretation
```

Not every experience must pass through every stage. When a stage occurs, PMM
should preserve the information needed to identify its authorship, inputs,
relationships, and promotion status. The stages must not be collapsed:

- an event is not its later interpretation;
- a reflection is not automatically a revision;
- a commitment is not its fulfillment;
- an outcome is not its later meaning;
- a repeated statement is not automatically a new act of identity or obligation.

## Cognitive aspiration and forensic discipline

PMM's aspiration is cognitive. A later cognition should be able to recover an
earlier experience, interpret it, reconsider a prior interpretation, inspect the
manner in which that interpretation was formed, and understand how this lineage
contributed to a present self-model. Identity is therefore neither the newest
self-description nor a flat sum of memories. It is a revisable reconstruction
of how remembered experience acquired meaning across time.

Commitments extend that reconstruction forward. They allow a system to relate
what it understands itself to have been, what it currently takes itself to be,
and what it intends to become. Later outcomes and reinterpretations can then
show whether that commitment was fulfilled, revised, abandoned, or understood
differently by a later version of the system.

PMM's implementation discipline is forensic. If the system claims that an
experience changed its self-understanding, which changed a commitment, which
later changed its interpretation of a former self, the architecture should make
each part of that lineage inspectable. Forensic rigor exists in service of the
cognitive aspiration; it is not the aspiration's replacement.

## Determinism boundary

PMM requires deterministic handling of recorded cognition:

- canonical preservation and serialization;
- provenance and explicit relationships;
- validation, rejection, and promotion decisions;
- authoritative state transitions;
- projection reconstruction and incremental convergence;
- retrieval selection and recorded provenance;
- replay of the history that actually occurred.

PMM does not require deterministic regeneration of model-authored cognition. A
model may produce a nondeterministic interpretation. Once recorded, PMM must
preserve what happened and deterministically govern how it can affect later
state.

These statements remain distinct:

1. A model produced an utterance.
2. PMM preserved the utterance in history.
3. PMM extracted a structured candidate.
4. A named validation policy accepted or rejected it.
5. PMM recorded a canonical event or failure.
6. A projection consumed that event.
7. An authorized consequence changed later reasoning or action.

Recording does not imply validation. Validation does not imply semantic warrant.
A canonical event does not automatically become authoritative state.

## Memory and relationship

Memory is not a flat archive. A useful reconstruction must be able to follow
explicit relationships among relevant events, including replies, evidence,
concept bindings, commitments, closures, outcomes, reflections, and revisions.

Four integrity questions must remain separate:

- **Referential integrity:** does the declared target exist?
- **Relational integrity:** may that target serve the declared role?
- **Semantic adequacy:** does the content genuinely warrant the interpretation?
- **Governance integrity:** which actor and production path may create or promote
  the relationship?

Existence does not establish role. Role does not establish meaning. Source labels
alone do not establish authority.

## Identity

Identity is reconstructed from history and relationships, not inferred from the
latest first-person statement. A defensible identity trace may include:

```text
proposal
  -> evidence and relevant relationships
  -> later interpretation or enacted commitment
  -> ratification
  -> governed adoption
  -> later revision or replacement
```

PMM must preserve the difference between an assertion about the user, an
assertion about another entity, and an assertion proposed for the agent's own
identity. Recurrence can be evidence worth governing, but repetition by volume
must not become identity automatically.

## Ontology and self-governance

Ontology is the system's revisable account of what kinds of things and
relationships matter, and where it locates itself within that structure. PMM's
goal is not merely to accumulate concept labels, but to preserve how concepts,
relationships, interpretations, and revisions contributed to that account.

Self-governance is the prospective side of reconstructed identity. A system can
use its remembered and interpreted history to make commitments about future
conduct, then examine later outcomes against those commitments. Operational
scheduling alone is not self-governance; the relevant identity, commitment,
outcome, and later interpretation must be reconstructably related.

## Commitments

A commitment is an explicit obligation across time. Its lifecycle must preserve
the act that opened it, its current state, closure provenance, later episodes,
and any outcomes or interpretations that are actually related to it.

A stable identifier may connect multiple open-to-close episodes, but shared
identifier text does not by itself prove that every episode expresses the same
semantic obligation. Current state and historical development must remain
distinguishable.

## Reflection and self-model

A reflection is a later interpretation of recorded material. It should identify
what it reflects on when that relationship matters. A deterministic summary,
counter, maintenance result, or diagnostic is not model-authored reflection
merely because it is useful to later cognition.

A recursive self-model must report the mechanism it actually computes. Lexical
counts, bounded signals, and projection deltas must not be described as deep
semantic introspection without corresponding implementation evidence.

## Retrieval and model-visible context

Canonical history, projected state, retrieval selection, and model-visible
context are different scopes. An event can exist in the ledger without being
selected, and a projection can be current without every underlying event being
rendered to the model.

Retrieval provenance explains why an event was selected. It does not establish
truth, authority, evidence quality, or semantic relevance.

## Operational records

Diagnostics, telemetry, summaries, counters, scheduling, and maintenance are
important infrastructure. They must not enter cognitive projections merely
because they share a convenient event kind or consumer path with interpretation,
identity, ontology, reflection, or self-governance.

Operational autonomy means that PMM can schedule and execute governed work. It
does not by itself establish reflective self-governance.

## Development rule

Every architectural change begins with one falsifiable guarantee and a complete
production-path audit. The audit must trace production, validation, rejection,
historical preservation, canonical recording, projection, retrieval, and
promotion, including alternate and fail-open paths.

A validator working when invoked is not a system guarantee. The strongest
supported conclusion is limited by the weakest relevant path.

Unsettled policy—including reference requirements, relation roles,
cardinalities, semantic adjudication, graph authority, schemas, and historical
migration—must remain explicit until separately selected and authorized.
