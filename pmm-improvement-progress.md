# PMM Current Status and Roadmap

**Audited runtime baseline:** `cbb477040d18fb443f681cee2d29b3d0ba9cd758`

**Status date:** 2026-08-20

This is the active project-status document. It records where PMM stands and what
comes next. Completed implementation history belongs in Git, not in an
ever-growing roadmap.

## Direction

PMM is building a reconstructable cognitive history around a language model:

```text
experience
  -> interpretation
  -> interpretation of interpretation
  -> identity, ontology, or policy revision
  -> commitment
  -> outcome
  -> later reinterpretation
```

The current implementation provides substantial infrastructure beneath that
lifecycle. It does not yet make the complete sequence a governed first-class
mechanism.

## Where the project is now

### Strong current substrate

- Canonical events are stored in a hash-linked SQLite ledger.
- Managed writers use database-scoped ownership and fencing.
- `Mirror`, `MemeGraph`, and `ConceptGraph` are required rebuildable projections
  with fixed-watermark freshness barriers.
- Managed turns preserve complete assistant output or an explicit terminal
  generation failure.
- One prior completed managed pair is rendered as bounded non-evidentiary
  conversational context.
- Retrieval combines concepts, graph topology, commitment episodes, summaries,
  and optional vector stages while recording selection provenance.
- Commitment opens and closes use transactional lifecycle guards and exact
  provenance on new assistant-produced events.
- A stable CID can expose separate current and historical open-to-close episodes
  without flattening them into one current obligation.
- Vector-overlap maintenance records bounded, attributable diagnostics without
  presenting them as complete retrieval verification.

### Important current limits

- Reference requirements and permitted roles are not governed uniformly.
- Declared evidence can be referentially valid without being relationally or
  semantically adequate.
- Unknown structured claim types still have a fail-open compatibility path.
- Identity adoption enforces temporal ordering but not anchor relevance or full
  actor/subject/object role separation.
- Reflection and self-model terminology still covers mechanisms with different
  cognitive meaning.
- Concept supersession lacks a complete ledger-aware relationship policy.
- Forced concept retrieval can include material without a separate relevance
  decision once a privileged concept has been seeded.
- Diagnostics, telemetry, summaries, and maintenance are not uniformly isolated
  from cognitive projections.
- The complete commitment-to-outcome-to-later-reinterpretation lifecycle is not
  yet mandatory.
- Semantic adequacy remains unresolved; typed structure does not prove meaning.

## Next task

### Reference-policy matrix audit

Create a current-main matrix of every reference-bearing structure before
changing runtime policy.

For each field and event type, record:

- every producer and alternate producer;
- whether the field is currently forbidden, optional, or required;
- structural and referential validation;
- permitted target kinds, ordering, identity, CID, token, version, and
  cardinality checks;
- rejection behavior and what historical form remains;
- every projection, retrieval path, and authoritative consumer;
- fail-open, compatibility, and silent-degradation paths;
- policy questions that remain unresolved.

The audit must include claims and evidence, reflection targets, identity
proposal/anchor/ratification/adoption relationships, concept supersession and
bindings, commitment open/close provenance and episode selection, terminal
managed-turn links, summaries, diagnostics, and retrieval records.

This is a read-only architecture audit. It does not authorize a schema,
migration, default change, semantic adjudicator, or runtime enforcement patch.

## After the matrix

Select one relational surface and define one falsifiable enforcement guarantee.
R06 identity-role separation is a plausible candidate because the current
identity structure cannot uniformly distinguish asserting actor, subject,
predicate, object, and evidence. The completed matrix must confirm the choice;
this roadmap does not pre-authorize it.

## Later candidates

These are unselected. Their order is not priority.

- Identity conflict, replacement, and coherence policy.
- Reflection-target and reinterpretation role integrity.
- Concept supersession and version-history integrity.
- Forced-concept relevance and attractor control.
- Complete hybrid-retrieval reproducibility or narrower vector-stage
  verification.
- Isolation of diagnostics, telemetry, summaries, and maintenance from cognitive
  projections.
- A governed commitment outcome and later-review lifecycle.
- Controlled generation retry policy.
- Further concept-authorship research only after its nonproduction stopping
  conditions are deliberately reopened.
- Continuity-fallback ablation only through its isolated experiment harness.

## Development rule

For each selected task:

1. establish repository state and one falsifiable guarantee;
2. trace every production, validation, preservation, projection, retrieval, and
   promotion path before editing;
3. identify policy choices explicitly;
4. implement only the authorized scope;
5. retrace the lifecycle after the change;
6. run focused and broader verification proportionate to risk;
7. inspect the exact diff and publication scope.

Documentation, passing tests, and model agreement cannot substitute for
production-path evidence.
