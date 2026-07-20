# PMM Cognitive Charter and Deviation Audit

## Status and authority

This document is the governing architectural baseline for the Persistent Mind
Model's cognitive direction. It records the purpose the PMM substrate exists to
serve and the current production deviations from that purpose.

Its authority order is:

1. The stated PMM purpose and intended cognitive mechanism recorded here.
2. The original philosophical architecture preserved in the repository.
3. Current production behavior, as evidence of what is implemented now.
4. `CONTRIBUTING.md` and later implementation documents.

Current production code remains authoritative when describing current behavior.
It does not redefine the intended architecture merely because it already exists.
`CONTRIBUTING.md` is the engineering contract beneath this charter and must not
compete with it.

Approved scope:

- The definitions and distinctions in this document are architectural policy.
- Current-state classifications are audit findings, not implementation decisions.
- The implementation freeze at the end of this document remains active.
- The current production architecture does not yet enforce or reliably preserve
  the complete recursive interpretive lifecycle as a first-class mechanism.

This document does **not** select event kinds, schemas, migrations, component
renames, historical reinterpretation, remediation order, or runtime changes.

## Purpose

PMM is an artificial-cognition architecture that enables a language model to
remember its history, interpret that history, reconsider its interpretations,
construct a revisable understanding of its current identity and ontology, make
commitments from that understanding, observe outcomes, and later reinterpret the
resulting history.

The governing lifecycle is:

```text
experience
  -> interpretation
  -> meta-interpretation
  -> identity or ontology revision
  -> commitment
  -> outcome
  -> later reinterpretation
```

Not every experience must advance through every stage. When a stage occurs, PMM
must be able to preserve and reconstruct its authorship, inputs, meaning,
relationships, and promotion status. The stages must not be collapsed into one
another.

## Determinism boundary

PMM requires deterministic:

- preservation of recorded cognition;
- provenance and authorship;
- reconstruction of what the model was shown;
- explicit relationships among cognitive events;
- validation and promotion decisions;
- authoritative state transitions and projections;
- replay of the resulting history.

PMM does not require deterministic regeneration of model-authored cognition.

A model interpretation may be nondeterministic when generated. Once produced,
it becomes a durable historical input that can be canonically recorded with the
information needed to reconstruct what occurred. Deterministic governance then
decides whether any consequence is eligible to enter authoritative identity,
ontology, commitment, policy, or other projected state.

The following statements remain distinct:

1. The model produced an interpretation.
2. PMM recorded it as a canonical historical interpretation.
3. PMM validated a declared relationship or proposed transition.
4. PMM promoted an authorized consequence into projected state.

Recording does not imply validation. Validation does not imply semantic warrant.
A canonical event does not automatically become authoritative state.

## Cognitive definitions

### Experience and history

History is the durable record of events. An experience is the information
actually made available to the model during a cognitive operation.

PMM must distinguish:

- history that exists in the ledger;
- events selected for the operation;
- immediate conversational context;
- system and governance instructions;
- user-provided or external information;
- generated outputs and operational results.

A model cannot be said to have experienced the entire ledger merely because the
ledger contained it. Reconstructing an experience requires the model-visible
inputs, their selection and rendering provenance, the applicable generation
configuration, and the resulting output.

### Interpretation

An interpretation is a model-authored semantic account of one or more
experiences, events, assertions, or earlier interpretations.

Its historical meaning depends on the author, its subjects, the information
available to that author, its content and qualifications, and the trigger that
caused it to be produced. Recording an interpretation does not automatically
make it an authoritative identity, ontology, or policy statement.

### Reflection

A reflection is an interpretation directed at the agent's own history, conduct,
state, commitments, or prior understanding.

A turn summary, counter, validation result, retrieval diagnostic, or maintenance
report is not a reflection merely because it describes the system or is stored
under a familiar label.

### Meta-reflection

A meta-reflection is a reflection whose subject includes an earlier
interpretation or reflection and which examines how or why that earlier
interpretation was formed.

It must preserve the distinction among the earlier subject, the prior
interpretation, the later revision trigger, the criteria being reconsidered, and
the resulting reinterpretation or reaffirmation. Counting or grouping reflection
records is not itself meta-reflection.

### Self-model and identity

A self-model is the current, revisable synthesis of adopted interpretations
concerning the agent's characteristics, roles, values, limitations, history, and
direction.

Identity is the governed continuity structure within that self-model. It is not
the latest self-description, a behavioral counter, an isolated token, or a label
that became current solely because a procedural sequence completed.

Identity must be reconstructed relationally across prior state, relevant
interpretations, revision triggers, proposals, adoption or rejection, later
commitments, outcomes, and subsequent reinterpretation. Historical identity
states remain part of the record when a later state supersedes or revises them.

### Ontology revision

Ontology revision is an explicit change in the concepts and relationships the
agent uses to understand itself and its world.

Concept occurrence, keyword detection, automatic indexing, graph binding, or
repetition does not by itself establish ontology development. A governed
ontology change must preserve the proposed meaning, authorship, prior state,
supporting interpretations or triggers, adoption status, and downstream effect.

### Commitment

A commitment is a prospective obligation made by a defined subject from a
particular understanding of its identity, ontology, circumstances, or goals.

Its cognitive continuity depends on its author and subject, motivating
interpretation, applicable state, intended action or result, evaluation criteria,
lifecycle, and later review. Opening and closing a durable task is useful
infrastructure, but does not alone establish this complete meaning.

### Outcome

An outcome is a later observation evaluated against an action or commitment.

It must distinguish what occurred, who observed it, which action or commitment
it evaluates, the evidence and criteria used, and whether the result motivates a
later interpretation or revision. A recorded success or failure flag does not by
itself complete the cognitive lifecycle.

### Autonomy and self-governance

Operational autonomy is the ability to schedule and execute work without a
contemporaneous user request.

Reflective self-governance is the ability to initiate the cognitive lifecycle,
reconsider adopted interpretations, form commitments from a current self-model,
evaluate outcomes, and revise future conduct under explicit governance.

A clock, scheduler, threshold controller, indexer, or maintenance loop can
support operational autonomy. It does not by itself establish reflective
self-governance.

### Diagnostics, telemetry, summaries, and maintenance

Diagnostics describe whether software mechanisms operated correctly. Telemetry
measures system activity. Summaries compress recorded information. Maintenance
operations preserve or tune infrastructure.

These records may later become explicit subjects of interpretation, but they are
not themselves interpretations, reflections, identity evidence, ontology
revisions, or commitments. They must not enter cognitive projections merely
because they share an event kind or convenient consumer path with cognition.

## Current deviation audit

The current PMM repository contains a strong persistence and governance
substrate and an incomplete or semantically blurred cognitive layer above it.

The strongest supported conclusion is:

> The current production architecture does not yet enforce or reliably preserve
> the complete recursive interpretive lifecycle as a first-class mechanism. It
> contains substantial supporting infrastructure and some informal or partial
> instances of the intended stages.

### Classification meanings

| Classification | Meaning |
|---|---|
| Faithful implementation | Implements the approved architectural meaning within a stated production scope. |
| Supporting infrastructure | Provides persistence, governance, retrieval, projection, scheduling, or other support without implementing the cognitive faculty itself. |
| Mislabeled mechanism | Its name or placement implies a cognitive faculty that its production behavior does not establish. |
| Partial implementation | Implements part of the intended lifecycle but does not preserve or govern the complete meaning. |
| Missing mechanism | The intended stage is not represented as a mandatory first-class production mechanism. |
| Conflicting rule | Documentation or governance language contradicts the charter or current production behavior. |

### Current faculty-level findings

| Intended faculty | Current production mechanism | Audit classification |
|---|---|---|
| Persistent history | Append-only, hash-linked EventLog and managed terminal outcomes | Faithful foundation within audited scopes |
| Relational memory | MemeGraph, ConceptGraph, retrieval provenance, event order, and commitment threads | Supporting infrastructure with partial relational integrity |
| Model experience | Persisted messages, retrieval selections, rendered context, and prompt telemetry | Partial implementation; the complete model-visible experience is not one canonical first-class record |
| Interpretation | Interpretive content may remain inside assistant utterances and structured fields | Missing as a governed first-class lifecycle |
| Reflection | Deterministic summaries, optional model-authored reflection fields, RSM reports, and diagnostics share `reflection` | Mislabeled and semantically overloaded mechanism |
| Meta-reflection | Windowed counts and graph statistics are emitted as meta summaries | Missing cognitive mechanism; existing behavior is supporting summary infrastructure |
| Self-model | Lexical tendencies, gaps, uniqueness measures, reflection intents, and concept metrics | Mislabeled deterministic telemetry rather than a semantic self-model |
| Identity | Structured proposal, temporal anchor, ratification, and token adoption | Partial implementation; ordering exists without complete relational or semantic revision |
| Ontology revision | Concept definitions, aliases, bindings, relations, and model or indexer tokens | Partial infrastructure; concept appearance does not establish governed ontology revision |
| Commitment | Durable open and close lifecycle with origin and projection support | Partial implementation; motivation from an interpreted self-state is not mandatory |
| Outcome | Operational outcome observations and commitment closure metadata | Partial implementation; the general interpretation-to-commitment-to-outcome chain is not enforced |
| Autonomy | Slot scheduling, deterministic decisions, indexing, summaries, and maintenance | Operational autonomy, not established reflective self-governance |
| Diagnostics and telemetry | Failure events, metrics, retrieval verification, stability, coherence, and maintenance records | Strong supporting infrastructure, but cognitive isolation is incomplete |

Current event names and component names remain historical production facts. This
classification neither renames them nor selects a replacement vocabulary.

### Current event-family findings

The production event vocabulary was audited on clean `main` at `8198e66`. The
classifications below describe current behavior; they do not approve replacements
or require historical reinterpretation.

| Classification | Current event kinds | Finding |
|---|---|---|
| Faithful historical preservation | `user_message`, `assistant_message` | Preserve utterance history within managed-turn boundaries, but do not alone reconstruct the complete model-visible experience. |
| Faithful diagnostic history | `generation_failure`, `validation_failure`, `violation` | Preserve operational or validation failures without promoting them as successful cognition. |
| Supporting measurement infrastructure | `metrics_turn`, `metric_check`, `metrics_update`, `autonomy_metrics`, `stability_metrics`, `coherence_check` | Record measurements and checks rather than cognitive faculties. |
| Supporting autonomy infrastructure | `autonomy_rule_table`, `autonomy_tick`, `autonomy_stimulus`, `autonomy_kernel`, `internal_goal_created` | Record scheduling, decisions, and maintenance rather than reflective self-governance. |
| Supporting persistence and retrieval infrastructure | `config`, `checkpoint_manifest`, `embedding_add`, `inter_ledger_ref`, `lifetime_memory` | Preserve configuration, replay acceleration, indexing, references, and compression. |
| Supporting test or fixture history | `filler`, `test_event` | Carry no defined cognitive meaning. |
| Mislabeled mechanism | `reflection` | Carries model observations, deterministic summaries, maintenance reports, RSM deltas, meditation output, and retrieval diagnostics under one cognitive label. |
| Supporting summaries with misleading surrounding terminology | `meta_summary`, `summary_update` | Record deterministic pattern and state summaries, not interpretation of interpretation or identity synthesis. |
| Partial structured assertion | `claim` | Preserves validated structured assertions on exercised paths; a claim is not automatically an interpretation or semantically warranted identity fact. |
| Partial identity mechanism | `identity_adoption` | Records procedural token adoption without establishing a complete coherent identity revision. |
| Partial commitment mechanism | `commitment_open`, `commitment_close` | Provide substantial lifecycle mechanics without mandatory derivation from a self-model or later reflective review. |
| Partial outcome mechanism | `outcome_observation` | Records operational outcomes without enforcing the general commitment-to-outcome-to-reinterpretation chain. |
| Mislabeled update mechanism | `policy_update`, `meta_policy_update` | Record deterministic suggestions; current production consumers do not apply them as authoritative policy mutations. |
| Partial ontology infrastructure | `concept_define`, `concept_alias`, `concept_bind_event`, `concept_relate`, `concept_bind_thread`, `concept_bind_async` | Preserve concept topology and attribution without establishing governed ontology revision. |
| Registered but not established in production | `concept_state_snapshot` | Is accepted by EventLog, but the audit did not locate a current production writer or authoritative consumer. |
| Supporting candidate history | `claim_from_text` | Preserves indexer-generated suggestions without promoting them into canonical claims. |
| Partial experience infrastructure | `retrieval_selection` | Records final selected IDs, scores, and provenance without one complete canonical record of every model-visible input or intermediate selection stage. |

### Current projection and service findings

| Mechanism | Classification | Strongest supported conclusion |
|---|---|---|
| EventLog | Faithful foundation | Provides canonical persistence, chaining, writer governance, and required projection-delivery machinery within audited scopes. |
| Mirror and LedgerMirror | Supporting infrastructure | Rebuild commitments, staleness, counts, configuration, and optional RSM state. |
| RecursiveSelfModel | Mislabeled mechanism | Derives lexical counters, gaps, uniqueness measures, reflection intents, and concept metrics rather than a semantic self-model. |
| MemeGraph | Partial relational infrastructure | Preserves useful reply, commitment, closure, and reflection topology; some relationships remain inferred, optional, or silently absent. |
| ConceptGraph | Partial ontology infrastructure | Preserves semantic bindings and relations without governing ontology revision or proving semantic warrant. |
| ContextGraph | Supporting or legacy infrastructure | Provides rebuildable context, thread, and tag projections but is not the authoritative managed-runtime relational graph. |
| AutonomyTracker | Supporting telemetry | Counts decisions and event kinds rather than measuring reflective self-governance. |
| CommitmentManager | Partial cognitive implementation | Provides a strong deterministic lifecycle without mandatory cognitive motivation and review relationships. |
| IdentityManager | Partial cognitive implementation | Enforces ordering and idempotence without establishing anchor relevance or complete identity revision. |
| AutonomyKernel | Operational autonomy | Implements scheduling, maintenance, indexing, summaries, metrics, and threshold suggestions rather than the complete reflective lifecycle. |
| Indexer | Supporting heuristic infrastructure | Creates keyword- or phrase-derived bindings and claim suggestions; those outputs are not model-authored cognition or semantic truth. |
| ConceptOpsCompiler | Partial implementation | Supports structured concept operations, but ordinary managed-turn metadata does not reliably deliver model-authored operations to it. |
| ReflectionSynthesizer | Mislabeled mechanism | Produces deterministic summaries under the `reflection` event kind. |
| MetaReflectionEngine | Mislabeled mechanism | Counts reflection and commitment records by windows; it does not perform meta-interpretation. |
| Identity summary | Mislabeled surrounding concept | Produces deterministic telemetry summaries rather than identity synthesis. |
| System primer and meditations | Partial informal implementation | Invite recursive and ontological interpretation, but prompts do not prove that the resulting cognitive lifecycle was preserved or governed. |
| Managed retrieval pipeline | Supporting infrastructure | Selects concept, thread, vector, and summary context with provenance; relevance and semantic adequacy remain unresolved. |
| Prior managed-pair rendering | Faithful continuity support | Makes one exact prior managed conversation available as bounded non-evidentiary context. |
| Context renderer | Partial experience reconstruction | Renders selected evidence and state without a general policy isolating every diagnostic record from cognitive context. |
| Lifetime memory | Supporting compression | Preserves bounded samples, concept handles, and commitment handles rather than a model-authored autobiographical interpretation. |

### Current production-order findings

The managed turn currently retrieves context, calls the model, preserves the
assistant utterance, creates bindings and retrieval diagnostics, synthesizes a
deterministic `reflection`, and may summarize before it processes the model's
commitments, claims, identity adoption, closures, and optional `REFLECT:` block.
The synthesized record therefore cannot represent the complete cognitive
consequences of that turn.

The live Mirror used by the managed runtime is also constructed without RSM
enabled. The context renderer consequently does not reliably feed the named RSM
snapshot into ordinary managed model turns. These are current audit findings,
not an approved repair design.

## Engineering consequence

Future work must answer separately:

1. What did the model or user emit?
2. What did PMM preserve as history?
3. What structured candidate was extracted?
4. What validation or governance decision occurred?
5. What canonical record was created?
6. What projection consumed it?
7. What became authoritative state?
8. What was later retrieved or made model-visible?

Referential validation establishes whether a declared target exists. Relational
integrity establishes whether it may serve a declared role. Neither proves that
the content semantically warrants an interpretation. Semantic adequacy must
remain explicit and unresolved wherever the implementation establishes only
structure.

## Implementation freeze

Until separately authorized governance and design decisions are complete:

- no R17 implementation;
- no reference-policy matrix implementation;
- no R06 or R07 enforcement;
- no new identity, reflection, ontology, commitment, or other cognitive semantics;
- no event-vocabulary or schema selection;
- no component renaming;
- no historical ledger migration or reinterpretation;
- no runtime remediation inferred from this charter.

Documentation may record current evidence, reconcile development rules with this
charter, and organize undecided work around the cognitive lifecycle. It must stop
before selecting or implementing runtime changes.
