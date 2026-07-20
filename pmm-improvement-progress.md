# PMM Improvement Progress and Remaining Work

- **Status date:** 2026-07-20
- **Audit basis:** The approved cognitive-architecture audit used clean, synchronized `main` at `8198e66d3bdfa10dfd5aaad298baac9187406556`, with divergence `0 0`. Earlier implementation and verification records retain their own stated revision boundaries.
- **Current recorded verification:** 468 tests passed; the final focused Stage 3 audit suite passed 43 tests; Ruff check and Ruff format check passed on all 24 Python files included in the Stage 3 verification scope; `compileall`, `git diff --check`, publication, and synchronization checks passed. Any verification rerun performed for this documentation-only update is reported separately below.
- **Scope:** Historical integrity, continuity, diagnostics, retrieval, and development-audit improvements, now re-baselined beneath the approved PMM cognitive architecture. This document records current evidence and undecided candidates; it does not select a runtime remediation sequence.

## Purpose

This document records the PMM improvements completed during the current development cycle, the narrow guarantees they establish, the boundaries they do not establish, the work still under consideration, and the process for further consultation with models operating both outside and inside PMM.

The work follows one rule: implement one small, observable, testable change at a time. Model recommendations are treated as operational feedback and design input, not as authoritative specifications. Each recommendation is checked against the source code before implementation.

## Governing architectural and audit lens

The [PMM Cognitive Charter and Deviation Audit](docs/PMM-COGNITIVE-CHARTER.md)
is now the governing architectural baseline. Its authority order is the stated
PMM purpose, the original philosophical architecture, current production
behavior as evidence of what exists, and then contribution and later
implementation documents.

PMM is developed through this lens:

> A self is an evolving network of remembered events, interpretations, relationships, and commitments that can reconstruct both its history and the relationships through which that history acquired meaning.

Memory is therefore not a flat archive. Identity must be reconstructed through a trace such as:

```text
event
  -> explicit relationship
  -> later interpretation
  -> revision or interpretation of that interpretation
  -> commitment
  -> outcome
  -> later interpretation
```

Events provide historical continuity; relationships provide context and meaning; interpretations provide a revisable present self-model; and commitments connect prior states to future action. A contradiction may be evidence of development only when the earlier interpretation, revision trigger, relationship, and resulting transition are traceable. An isolated self-description is historical content, not sufficient identity evidence.

This philosophical lens guides questions for the implementation; it does not prove that the implementation answers them. Current production code remains authoritative when describing current behavior. It does not redefine the intended architecture merely because it already exists. The deep research report in `docs/deep-research-report.md` is retained as architectural and philosophical source material, not as the governing specification.

The charter also establishes the determinism boundary:

> PMM requires deterministic preservation, reconstruction, relationships,
> validation, promotion, projection, and replay of recorded cognition. It does
> not require deterministic regeneration of model-authored cognition.

Model-authored interpretation may be nondeterministic when produced. Once
recorded, its historical form and applicable provenance become part of the
canonical record, while promotion into authoritative state remains governed and
deterministic.

The governing engineering rule is:

> A validator's correctness when invoked does not establish a system guarantee. Every relevant production and promotion path must also be checked for omission, bypass, weakening, fail-open behavior, and silent degradation.

The document uses the following lifecycle rather than the ambiguous words “stored” or “accepted”:

```text
utterance history
  -> extracted candidate
  -> validation result
  -> canonical event or distinct failure event
  -> deterministic projection
  -> authoritative promotion or state mutation
```

It also keeps two pairs of distinctions explicit:

- A **coverage gap** exists when a path that should be checked can omit or bypass the check. An **enforcement gap** exists when supplied structure reaches the check but is not tested against the repository state or required role.
- **Referential validation** asks whether a declared referent exists. **Relational integrity** asks whether that referent may serve the claimed role. **Semantic adequacy** asks whether its content genuinely warrants the interpretation. **Governance integrity** asks which actors and paths may create or promote it.

Existence does not establish role, and role does not establish semantic warrant. The strongest system-wide conclusion is limited by the weakest relevant production or promotion path.

## Current status

The twelve earlier runtime improvements remain complete. Three later integrity closures—R08, C01, and C02—have also been completed and published. The evidence-availability branch, prompt-growth telemetry, duplicate-primer correction, managed-turn terminal-outcome protocol, provider-enforced output budgets, authoritative commitment-close transitions, shared-graph startup reconstruction, immediate managed-turn continuity, fenced database-scoped writer governance, and fixed-watermark required-projection freshness are complete within the scopes described below.

The architecture audit that followed the twelve earlier runtime improvements did not itself change runtime code. It clarified the boundary between temporal ordering, referential checks, relational integrity, and semantic adequacy, and produced one repository-scoped development-audit skill plus mandatory agent routing. Those development controls are described separately from the twelve runtime improvements.

The later Cognitive Charter audit also changed no runtime code. It established
that PMM retains a strong persistence and governance substrate while its
cognitive layer remains incomplete or semantically blurred. Current labels such
as reflection, recursive self-model, identity adoption, ontology development,
and autonomy must therefore be evaluated by their production mechanisms rather
than treated as proof that the corresponding cognitive faculties exist.

The current integrity position is:

| Layer | Strongest supported conclusion |
|---|---|
| Historical preservation | On the audited managed-runtime terminal path, complete assistant utterances are retained. Parsed candidates rejected by the runtime validator also produce distinct `validation_failure` events; they do not produce canonical `claim` events. Malformed claim lines remain in utterance history but may never become extracted candidates or typed failures. |
| Referential validation | Implemented for declared `evidence_events` and formal evidence designations on the audited runtime path, but coverage is conditional and uneven across reference-bearing structures. |
| Deterministic relational integrity | Partially implemented. PMM records useful typed edges and ordering, but identity anchors, reflections, supersessions, and evidence roles do not yet receive uniform permitted-role checks. |
| Operational conversational continuity | The immediately preceding completed protocol-v1 managed pair is selected from the shared MemeGraph, exactly dereferenced from the canonical ledger, and rendered as bounded non-evidentiary context. This does not expand evidence availability or establish semantic relevance. |
| Canonical writer governance | Audited canonical writer paths require a live, database-scoped owner and fencing token. Transactional predecessor selection and insert-trigger enforcement prevent audited competing managed writers from silently overlapping or forking the hash chain. |
| Projection-delivery integrity | Required managed-runtime projections are rebuilt and reconciled by canonical replay through a fixed watermark. Required delivery failure is durable and fail-closed; optional listeners remain non-authoritative. |
| Semantic adequacy | Unresolved. PMM does not establish that an existing or selected event genuinely supports a claim or warrants an interpretation. |

The relational memory substrate is currently richer than the recursive introspection mechanism. `MemeGraph`, `ConceptGraph`, retrieval provenance, commitments, and event ordering preserve substantial topology. `RecursiveSelfModel` primarily derives bounded counters, lexical-marker tendencies, sliding-window gap signals, hash-prefix uniqueness, and recorded reflection intents. `Mirror` can compare those deterministic projections across time. Together they can establish that recorded patterns changed; they do not yet establish a deep semantic explanation of why an interpretation changed.

The remaining items are a mixture of operational backlog candidates and integrity-policy decisions. Model consultation may generate useful hypotheses, but mechanically specifiable gaps now require repository inventory and explicit policy choices rather than more model consensus.

Recent exploratory use exposed additional backlog candidates in retrieval verification, relational-role representation, and forced-concept relevance. These findings do not contradict the closed continuity and governance guarantees; they concern diagnostic validity, representational adequacy, retrieval policy, and semantic interpretation. C02 makes the immediately prior managed conversation available, and Stage 3 governs writers and projection freshness, but neither guarantees correct relational-role assignment, current-query relevance for forced context, or semantic adequacy.

## Completed improvements

### 1. Structured generation results and failure isolation

Adapters now return a structured `GenerationResult` containing:

- Visible response text
- A status of `complete`, `empty`, `truncated`, or `indeterminate`
- Provider-supplied completion metadata

Ollama completion status is derived from `done` and `done_reason`. OpenAI completion status is derived from `finish_reason`.

Established invariant:

> Only a generation with `status == "complete"` may create an `assistant_message` or reach semantic parsers.

All other results create a `generation_failure` event. The event may retain a partial visible response and safe diagnostic metadata, but it does not store private thinking content. Failed generations cannot create commitments, claims, identity changes, reflections, or concept bindings.

### 2. Structural validation of identity-claim ingress

`identity_proposal` and `identity_ratify` no longer pass through the generic “unknown claim type” acceptance path.

Identity claims now require:

- An object-shaped payload
- A non-empty string `token`
- Only fields supported for that identity-claim type
- A non-empty proposal description when one is supplied
- A structurally valid proposal `evidence_events` list when one is supplied

`identity_proposal` currently allows `token`, optional `description`, and optional `evidence_events`. `identity_ratify` currently allows only `token`; supplying evidence or a description on a ratification makes the structure invalid.

This closes the original “magic words with parseable JSON” hole at the audited claim-ingress boundary. It does not make evidence mandatory, establish that evidence is relevant, or ground the resulting identity transition. The ratification evidence asymmetry is an unsettled policy issue, not an intentional guarantee inferred by this document.

### 3. Temporal identity-adoption ordering

Identity adoption now requires the following ledger order:

```text
validated identity_proposal
        ↓
reflection or commitment lifecycle event
        ↓
validated identity_ratify for the same token
```

The anchor must occur strictly between proposal and ratification. Reversed claims, unvalidated claim events, and proposal-plus-ratification without an intervening anchor cannot create an adoption.

Each adoption records:

- Proposal event ID
- Anchor event ID
- Anchor kind
- Ratification event ID

Existing identity-adoption events remain immutable and idempotent.

Supported boundary:

> The current anchor requirement proves temporal order, not relational relevance.

`maybe_append_identity_adoptions` treats any intervening `reflection`, `commitment_open`, or `commitment_close` as an anchor. It does not require that event to identify the proposal, token, or identity thread. The strongest supported conclusion is therefore **ordering implemented and mandatory for manager-produced adoption; anchor relevance not implemented**.

The relational projection is weaker still: `MemeGraph` does not consume the recorded `anchor_event_id` when creating `adopts_identity_for`; it links an adoption to the most recent assistant message or reflection. The adoption record and projected graph edge therefore do not establish one authoritative anchor relationship. `IdentityManager` also trusts claim events marked `validated: true`; the current in-repository production writer is `RuntimeLoop`, but any future alternate writer must preserve the same validation boundary rather than setting that metadata directly.

### 4. Retrieval provenance recording

Every selected retrieval event can now carry deterministic reason tags:

- `forced_concept`
- `sticky_concept`
- `summary_pinned`
- `concept_binding`
- `thread_expansion`
- `summary_expansion`
- `vector_refinement`
- `summary_vector`
- `graph_expansion`

Actual deterministic vector scores are retained when applicable. The aligned provenance records are persisted in `retrieval_selection` events for audit and replay analysis.

This change explains selection without changing selection order or retrieval limits.

### 5. Conditional referential validation of declared evidence events

On the audited runtime claim path, a structured claim containing `evidence_events` is checked against the ledger before the claim is persisted.

Established invariant:

> A claim may omit `evidence_events`, but every event ID it explicitly supplies must already exist at validation time.

Behavior:

- Existing IDs are accepted.
- An empty list is accepted.
- Duplicate valid IDs are accepted.
- Any missing ID rejects the complete claim.
- Mixed existing and missing IDs reject the complete claim.
- Boolean, string, zero, negative, and otherwise malformed IDs are rejected.
- A claim cannot cite its own eventual claim-event ID because that event does not exist during validation.

Omission returns success with “no evidence references declared.” This is a coverage boundary, not a failure of the existence check when invoked. On the normal runtime path, supplied IDs are also checked against the current turn's selected raw-event set. These are referential-existence and availability checks only: PMM does not establish that a cited event is permitted to serve the declared role or that it semantically supports the claim. Which claim types require nonempty evidence belongs to an explicit policy matrix that has not yet been adopted.

### 6. Retrieval provenance rendered to the model

The selected model now receives a `Retrieval Selection Mechanics` section showing why each evidence event appeared and any applicable retrieval score.

The section explicitly states:

> These fields explain why an event was selected. They do not establish truth, authority, confidence, or evidence quality. Similarity scores measure retrieval relevance only.

This changes provenance from a ledger-only audit facility into information the model can reason about while preventing a high similarity score from being framed as proof.

### 7. Typed claim-validation diagnostics and promotion separation

Parsed claim candidates rejected by `validate_claim_detailed` now create a canonical `validation_failure` event with:

- Claim type
- Attempted structured data
- Stable reason code
- Human-readable reason
- Link to the originating assistant event

Current reason codes include:

- `MISSING_EVIDENCE`
- `INVALID_EVIDENCE_STRUCTURE`
- `INVALID_IDENTITY_STRUCTURE`
- `MISSING_EVENT`
- `COMMITMENT_MISMATCH`
- `INVALID_REFERENCE`

The originating `assistant_message` remains immutable utterance history. A validator-rejected candidate is preserved separately in `validation_failure`, but no canonical `claim` event is emitted and no claim-derived ConceptGraph binding or identity adoption is produced from that candidate. This is the canonical example of historical preservation without authoritative promotion.

This guarantee is scoped to candidates that were successfully extracted and passed to the validator. If any exact-prefix claim line contains malformed JSON, `_extract_claims` catches the extraction error and returns no candidates for that response; the assistant utterance remains preserved, but no typed claim-validation failure is created. Existing narrative reflection behavior remains for compatibility; where a typed failure exists, it is the authoritative diagnostic.

### 8. Formal evidence-availability validation

PMM now distinguishes between an event that exists in the ledger and an event that was actually available to the model during the turn in which it made a formal evidence claim.

Models may emit an optional `evidence_designations` array in the first-line structured JSON header:

```json
{"evidence_designations":[{"event_id":17,"supports":"selected_seed"}]}
```

The field is optional. Its absence means that the response makes no formal evidence designations. Event numbers in ordinary prose remain ordinary prose and are not parsed as evidence claims. Broken first-line JSON is also treated as prose because PMM does not infer structured intent from malformed text.

Established invariant for formally declared evidence on the audited runtime path:

> PMM verifies that formally designated event evidence existed and was selected for the current turn's raw-event evidence channel. It does not determine whether that evidence is permitted in the claimed role or whether it proves or semantically supports the associated assertion.

Validation behavior:

- Parsing and validation occur after complete generation but before the immutable `assistant_message` is appended.
- Every designated `event_id` must be a positive integer in the current turn's retrieval selection.
- Each designation requires a non-empty `supports` identifier.
- Validation is all-or-nothing; one malformed or unselected designation rejects the complete designation array.
- Valid designations are stored in the originating assistant event's metadata.
- Rejected designations create a typed `validation_failure` after the assistant event, linked through `about_event`.
- Existing `CLAIM` payloads containing `evidence_events` must satisfy both referential existence and current-turn selection, preventing claims from bypassing the same availability boundary.

New reason codes are:

- `INVALID_EVIDENCE_DESIGNATION_STRUCTURE`
- `EVIDENCE_NOT_SELECTED`

The implementation is recorded in commit `fdd3f78` (`Validate formal evidence availability`).

An isolated integration test used `/tmp/pmm-evidence-final.d0glmD/pmm.db`, leaving the configured production/experimental ledger unchanged. Three no-marker runtime turns created ordinary events, and a controlled concept fixture made event 17 retrievable while events 6 and 27 remained unselected.

In the mixed designation case:

- Retrieval selected exactly event 17.
- The response formally designated selected event 17 and existing but unselected event 6.
- Event 27 appeared only in prose.
- PMM persisted no validated designations and created `EVIDENCE_NOT_SELECTED` for event 6, linked to the originating assistant event.
- The prose reference to event 27 caused no validation action.

In the claim-bypass case:

- Retrieval again selected exactly event 17.
- A `CLAIM` cited existing but unselected event 6 through `evidence_events`.
- PMM persisted no claim and created `EVIDENCE_NOT_SELECTED`, linked to the originating assistant event.

The isolated final ledger created no commitments or identity mutations. That is a recorded outcome of these controlled responses, not an independent success criterion: appropriate commitments can represent valid ontological crystallization in PMM. The results confirm raw-event availability enforcement, all-or-nothing behavior, prose isolation, and auditable failure linkage for the exercised runtime paths. They do not prove universal coverage for every reference-bearing structure.

Explicit semantic limitation:

> Selection proves only that the event was included in the turn's raw-event evidence channel. PMM also renders derived CTL, thread, graph, identity, self-model, and commitment-state projections whose underlying events may not all be selected as raw evidence. PMM does not yet prove that event 17 truly supports `selected_seed`, nor does it infer evidentiary meaning from unrestricted natural language.

### 9. Prompt-growth telemetry

PMM now records bounded prompt-construction measurements in the existing diagnostic event for each generation. Successful generations store them in `metrics_turn.meta.prompt_telemetry`; failed generations store equivalent measurements in `generation_failure.meta.prompt_telemetry`.

The `prompt_telemetry.v1` payload records:

- PMM system-primer insertion count and character count
- Rendered PMM-context character count
- Retrieval-provenance character count
- Raw-evidence character count
- Current user-message character count
- Total assembled-prompt character count
- Selected evidence-event count
- Provider-reported prompt-token count when available
- Configured context-window size when known

Unknown provider token counts and context-window sizes remain `null`. Measurements are stored without duplicating prompt contents, and the observational patch does not change prompt assembly, retrieval, truncation, or token budgeting.

The implementation is recorded in commit `b799abf` (`Add prompt growth telemetry`). Its controlled fixture exposed two PMM-owned primer insertions totaling 4,224 characters, making a previously hidden prompt-composition defect directly observable.

### 10. Single ownership of system-primer insertion

The duplicate-primer audit established an explicit adapter contract:

> `system_prompt` is the complete provider-facing system policy.

`RuntimeLoop` now owns PMM policy composition. Ollama and OpenAI adapters translate and transmit the completed prompt without injecting another primer. Custom adapters continue to receive the primer through runtime composition. In-repository direct adapter usage was audited; the only direct built-in adapter caller is a connectivity check that does not rely on generated policy content.

Regression coverage proves that runtime composition, Ollama requests, and OpenAI requests contain exactly one primer; custom adapters retain it; telemetry reports one insertion and 2,112 primer characters; and model input changes only by removal of the redundant copy. Retrieval, parsing, ledger, and validation behavior were not modified by the correction.

The implementation is recorded in commit `fe815fe` (`Remove duplicate system primer injection`).

A matched fresh-database experiment compared the telemetry commit with the corrected commit using `granite4.1:8b-q5_K_M`, temperature zero, the same prompt, equivalent initial ledgers, and the same unset seed configuration:

| Measurement | Duplicated primer | Single primer |
|---|---:|---:|
| Primer insertions | 2 | 1 |
| Primer characters | 4,224 | 2,112 |
| Total prompt characters | 6,801 | 4,687 |
| Provider prompt tokens | 1,387 | 977 |
| Response characters | 1,280 | 785 |
| Provider output tokens | 238 | 148 |
| Selected evidence events | 0 | 0 |
| Control markers | `COMMIT: acknowledgment_of_no_evidence` | None |
| Ledger mutations | One `commitment_open` (`acknowledgment_of_no_evidence`) | None |
| Invented event references | None | None |

The corrected run used approximately 30% fewer provider prompt tokens and one-third fewer assembled-prompt characters. It also produced a shorter response without losing the requested behavior. The duplicated-primer run emitted `COMMIT: acknowledgment_of_no_evidence`; the corrected run emitted no marker. This is a behavioral observation, not evidence that commitment absence is preferable. Determining whether the commitment was meaningful would require inspecting its declared versus runtime-assigned concepts and its later retrieval, reflection, development, and closure behavior.

Behavioral limitation:

> The adapter exposes no explicit numeric seed setting, so both conditions reported `seed: null`. Behavioral differences are observations rather than strict causal proof. The architectural result is definitive: PMM policy is composed exactly once.

### 11. Managed-turn terminal outcomes

PMM now marks runtime-managed user turns and their terminal outcomes with `turn_protocol: terminal_outcome.v1`. Every managed turn has exactly one linked terminal outcome through `about_event`: a successful `assistant_message` or a `generation_failure` describing a returned incomplete result, an actively observed transport error, or a later-recovered interruption.

Established invariant:

> Every runtime-managed user turn using terminal-outcome protocol v1 has exactly one linked terminal outcome. A caught active failure is recorded as `transport_error`; a termination inferred by a later runtime is recorded as `interrupted`.

All protocol-v1 terminal paths use one transactional `EventLog` operation. A protocol-scoped SQLite unique index and `BEGIN IMMEDIATE` transaction make competing recovery attempts converge on one outcome. Legacy events, including older uses of `about_event`, remain outside the new uniqueness rule and are never rewritten or automatically classified merely because they lack protocol metadata.

Recovery is intentionally narrow. Runtime initialization examines only the latest user event and recovers it only when it opts into protocol v1, has no linked terminal outcome, and is followed solely by its recognized pre-generation embedding side effect. Ambiguous suffixes and legacy turns remain unchanged. The original terminal-outcome implementation did not itself solve cross-process ownership. Stage 3 later strengthened its operating precondition: recovery now runs only after the runtime has obtained fenced database-scoped ownership and confirmed required-projection freshness. A live competing owner excludes a contender, so the contender cannot prematurely recover that owner's in-flight turn. Terminal-outcome uniqueness and meaning are unchanged; the later governance layer prevents competing managed writers from overlapping silently.

Adapters may raise a safe typed `AdapterTransportError` containing content-free request measurements known before I/O. Runtime combines those measurements with context, provenance, evidence, user-message, and selection measurements already available locally. Arbitrary adapter exceptions still produce a terminal failure, but unavailable provider measurements remain `null` and exception messages, tracebacks, prompt contents, and response bodies are not persisted.

The implementation is recorded in commit `17cc164` (`Guarantee terminal outcomes for managed turns`). Verification included:

- Two SQLite connections racing recovery produced exactly one terminal event.
- A copied 152-event legacy database migrated without rewriting history or recovering its unmarked historical incomplete turn.
- The copied ledger accepted a new linked protocol-v1 turn normally.
- An isolated real-Ollama deadline test produced exactly `user_message → embedding_add → generation_failure`.
- The real transport failure retained safe prompt telemetry and created no assistant message, commitment, claim, reflection, identity change, or other semantic mutation.

The operational audit that motivated this change also observed an Ollama generation producing approximately 13,056 tokens before the adapter's 180-second read timeout cancelled it. Output limiting was kept separate from terminal accounting and implemented as the next bounded improvement.

### 12. Provider-enforced output budgets

PMM now supports an optional provider-neutral `output_budget_tokens` setting. The value can be supplied through CLI and MCP arguments or `PMM_OUTPUT_BUDGET_TOKENS`; explicit arguments take precedence over the environment. When unset, provider requests remain backward compatible and no explicit output budget is added.

Established invariant:

> A configured output budget is enforced by a capable provider adapter, and a provider-reported length-limited result produces an auditable truncated terminal failure rather than a successful partial turn.

Ollama maps the setting to `options.num_predict`. OpenAI Chat Completions maps it to `max_completion_tokens`, which may include both visible and reasoning tokens. An adapter must explicitly declare budget support and accept the resolved value. If a budget is configured for an unsupported custom adapter, PMM fails before appending the managed user event; legacy custom adapters remain compatible when the setting is absent.

Successful and failed turns record `output_telemetry.v1` containing:

- Configured output budget
- Provider-reported aggregate output-token count when available
- Provider-reported reasoning-token count when available
- Raw safe provider stop reason
- Whether the provider reported that a length limit was reached

Unavailable reasoning counts remain `null`, including for Ollama. PMM does not infer that a configured budget specifically caused a `length` stop; it records `provider_stop_reason: length` and `length_limit_reached: true`. Partial visible output, including reasoning-only exhaustion with no visible response, remains isolated from semantic parsers.

The implementation is recorded in commit `7490928` (`Enforce provider output budgets`). An isolated real-provider test used `granite4.1:8b-q5_K_M` with a budget of eight tokens and a deliberately long prompt. Ollama returned `done_reason: length` and `eval_count: 8`. PMM persisted exactly `user_message → embedding_add → generation_failure`, linked the truncated outcome to the managed turn, retained the partial response diagnostically, and created no assistant message or semantic mutations. The isolated ledger is `/tmp/pmm-output-budget.Uo8WYB/pmm.db`.

The current implementation exposes an explicit override but leaves the budget unset by default. That is technically backward compatible but not the intended zero-configuration product behavior. The next design step is a deterministic automatic budget for built-in capable adapters, while retaining explicit overrides only as advanced escape hatches.

## Later continuity and integrity closures

### R08 — authoritative commitment-close semantics

R08 closed at `adf3e57df35f8141b9a88f72e6be0b548286b18e` (`Enforce authoritative commitment close semantics`).

Established invariant:

> A canonical commitment close is an idempotent transition from one exact existing open commitment event, not a free-standing assertion that an arbitrary CID was closed.

`CommitmentManager` routes assistant, autonomy, and internal closure producers through `EventLog.append_commitment_close()`. That operation requires a non-empty production source, reserves the write transaction, resolves the latest lifecycle event for the CID, and creates a close only when that event is an open. An unknown CID creates no event. Repeating a closure returns the existing close without creating another. Each new close records `open_event_id`, and the partial unique index prevents two new authoritative closes from targeting the same open event. `MemeGraph` reconstructs the corresponding `closes` edge to that exact open event rather than guessing from the CID.

Verification covered unknown-CID rejection, exact source and open-event recording, repeated-close idempotence, concurrent close convergence, producer migration, and live/rebuilt graph parity. R08 establishes authoritative transition mechanics; it does not establish that the commitment was wise, fulfilled in substance, or semantically supported by its stated outcome.

### C01 — shared MemeGraph startup reconstruction

C01 closed at `e2caabf4d0556777eb12ac10094d1137ec84e614` (`Rebuild MemeGraph on runtime startup`).

Established invariant at that revision:

> Complete tracked-history reconstruction of the shared `RuntimeLoop.memegraph` occurs before its first production consumer. Reconstruction uses an atomic EventLog reconstruction-to-listener handoff and runtime initialization fails when required reconstruction fails.

At the C01 revision, narrow interrupted-turn recovery ran first so any recovered terminal event was included in the graph snapshot. `EventLog.rebuild_and_register_listener()` then held the EventLog lock across ordered snapshot reconstruction and listener registration. An append was therefore either present in the snapshot or delivered incrementally; reconstruction failure propagated and prevented service initialization. The graph was complete before retrieval, lifetime-memory, autonomy, and other `RuntimeLoop` consumers, and one-shot, MCP, replay, and ordinary `RuntimeLoop` construction inherited that initialization path. Tests covered reopened history and relationships, graph availability at first retrieval, the atomic append handoff, initialization failure, replay parity without hash mutation, and consecutive one-shot and MCP invocations.

Stage 3 later strengthened and reordered the current initialization sequence. At `69cbe30`, the fenced runtime first rebuilds its required MemeGraph, Mirror, and ConceptGraph projections and confirms a fixed-watermark barrier; only then may interrupted-turn recovery mutate the ledger, followed by another barrier. Duplicate delivery at or below each projection's acknowledged watermark is suppressed. Thus “recovery before graph reconstruction” remains an accurate description of the original C01 revision, but not of the current governed runtime. The current ordering makes fenced ownership and required-projection health prerequisites for recovery while preserving C01's complete-before-consumer guarantee.

C01 proves structural reconstruction and delivery continuity. It does not prove that a graph edge is semantically adequate or that every historical relationship has a uniformly validated role.

### C02 — graph-guided conversational continuity and fenced ledger governance

C02 stages 1 and 2 closed at `5570150ea63b816861d875c9487dfea7211d5184` (`Restore graph-guided turn continuity`). Their production path is:

```text
Canonical EventLog
  -> indexed relational projection
  -> bounded structural selection
  -> exact canonical dereference
  -> non-evidentiary conversational rendering
```

Established stages 1–2 invariant:

> The immediately preceding completed protocol-v1 managed pair is resolved through the shared MemeGraph, dereferenced as exactly two canonical EventLog records, and rendered as bounded non-evidentiary conversational context.

For managed assistant events, `replies_to` uses canonical `meta.about_event`; the latest-user heuristic remains a legacy-only behavior and is not promoted into the managed-pair index. Rebuild and incremental delivery maintain the same sorted assistant index and assistant-to-user mapping, including duplicate and unexpected out-of-order delivery handling. Lookup selects one prior completed managed pair without scanning all graph nodes or ledger rows. `EventLog.get()` dereferences exactly those two IDs. Rendering filters recognized assistant scaffolding, applies deterministic bounded truncation, excludes the current user and non-pair runtime events, deduplicates independently selected retrieval overlap, and records content-free telemetry. Live and reopened runtimes produce the same result at the same boundary, and one `RuntimeLoop` mechanically serializes its complete managed turns.

The prior pair is conversational visibility, not evidence. Its IDs are not added to retrieval selection, provenance, `selected_event_ids`, evidence-designation availability, or claim `evidence_events` availability. Existing retrieval remains authoritative for evidence availability. Tests cover canonical managed linkage, legacy exclusion, rebuild/incremental equivalence, bounded exact dereference, filtering, deterministic truncation, deduplication, evidence separation, live/reopened parity, and same-runtime turn serialization.

C02 Stage 3 closed at `69cbe30d49d817afb8cc1fdf1fdee4865a2f586f` (`Enforce fenced ledger governance`).

Established Stage 3 invariant:

> C02 Stage 3 is implemented and mandatory for audited managed-runtime paths. Canonical writes require a live fenced database-scoped writer session, and graph-derived state requires confirmed fixed-watermark projection freshness. Competing managed writers fail explicitly or acquire only after release or expiry.

Each governed database has persistent identity and a singleton lease carrying owner, role, expiry, heartbeat, and a monotonically increasing fence. A writer acquires without hidden waiting; a live owner produces `WriterOwnershipConflict`, while a busy acquisition reservation is also explicit. An independent heartbeat keeps the lease live through provider generation. A shared reentrant operation gate serializes same-owner services. Reader and writer construction roles are explicit, owned one-shot lifetimes release deterministically, and expiry permits takeover with a higher fence without restoring authority to the stale owner.

Every canonical append path reserves with `BEGIN IMMEDIATE`, validates the owner, fence, live lease, and database clock, selects the canonical predecessor inside that transaction, and commits the new hash-linked row. A SQLite insert trigger checks connection-registered owner and fence functions against the live lease, mechanically rejecting unowned inserts on governed connections. Provider results are rechecked after generation and discarded after ownership loss.

Required projection registrations track an acknowledged `applied_through` watermark. Before graph-dependent work, a barrier fixes the canonical ledger boundary and replays every missing canonical event through it; freshness does not depend on process-local callback delivery or on merely observing the largest event ID. Required rebuild or delivery failure records durable projection health, poisons the writer session, and stops further managed work. A typed post-commit failure reports that the canonical event exists, its ID, owner and fence, the failed projection, and the last confirmed watermark, distinguishing it from an uncommitted append failure. Optional listeners remain best-effort and cannot suppress nested required-delivery failure.

The production audit covered runtime, one-shot, MCP, autonomy, metrics, maintenance, backfill, and experiment writer constructors and graph consumers. The final focused Stage 3 audit suite covered ownership and trigger enforcement, hidden-wait exclusion, hash-fork prevention, heartbeat and lease loss, expiry and takeover, stale provider-result rejection, recovery exclusion, fixed-watermark barriers, durable required-listener failure, post-commit error semantics, one-shot contention, and MCP contention. The complete suite recorded 468 passing tests.

No bypass was found among the audited production constructors, append APIs, and graph consumers. This does not claim protection against hostile schema modification, forged connection functions, or arbitrary out-of-band SQLite administration.

Stage 3 is governance and projection-delivery integrity. It does not make graph selection semantically relevant, promote conversational context to evidence, prove claim truth, validate identity coherence, or establish semantic adequacy.

## PMM development-audit controls

The architecture review produced a repository-scoped development skill at `.agents/skills/pmm-development-auditor/`. This is deliberately not a PMM runtime reasoning skill and is not counted as a thirteenth runtime improvement. Its purpose is to make coding and review agents determine exactly what the current repository establishes before they describe, modify, or extend a PMM guarantee.

The skill contains:

- A procedural `SKILL.md` with the audit workflow, evidence hierarchy, mandatory finding format, conclusion vocabulary, pre-change audit, and post-change retracing requirements
- `references/philosophical-foundations.md`, which preserves the relational identity premise without using philosophy as implementation proof
- `references/architecture-map.md`, which identifies likely production surfaces while explicitly remaining a navigation aid
- `references/integrity-and-promotion.md`, which defines lifecycle layers, coverage and enforcement gaps, integrity classes, and promotion boundaries
- `references/audit-cases.md`, which defines transferable cases for omitted checks, unchecked targets, false roles, preservation without promotion, and silent degradation
- `agents/openai.yaml`, which supplies the skill's discovery metadata and default invocation prompt

The skill requires agents to record repository state, state a falsifiable guarantee, trace every producer and consumer through preservation and promotion, search for alternate and fail-open paths, inspect tests only after production control flow, and report the strongest conclusion supported by the weakest relevant path. Its evidence order is:

1. Current production code paths
2. Schemas and deterministic projections
3. Tests exercising those paths
4. Runtime or ledger evidence
5. Documentation and design artifacts
6. Model or agent descriptions

Root `AGENTS.md` now requires `$pmm-development-auditor` for PMM architecture, runtime, validator, claim, relationship, projection, identity, commitment, retrieval, documentation, and guarantee work. It also requires both pre-change and post-change audits. The rule is scoped: unrelated repository maintenance does not invoke the auditor unless it enters those concerns.

Verification completed for the development control itself:

- The skill package passes the skill-creator structural validator.
- A freshly rendered Codex prompt discovers the skill from `.agents/skills`.
- The same prompt contains the root `AGENTS.md` requirement to invoke it for PMM work.
- The reference links and `openai.yaml` metadata resolve and parse.

The four blind cases were successfully completed against the preceding skill draft. They demonstrated diagnostic transfer across optional omission as a coverage failure, an unchecked populated reference as a referential enforcement failure, real identifiers used in a false relational role, and preservation without canonical promotion.

Repository-state capture and mandatory post-change retracing were added after those blind runs. They have since been exercised in real repository work, including the C01 and C02 cycles: clean synchronized pre-change gates, production-path and bypass audits, narrow authorization boundaries, implementation, post-change lifecycle retracing, focused and complete test verification, staged-diff review, and clean synchronized publication. Those later cycles are operational evidence for the full audit discipline; they are not retroactively classified as blind tests. The earlier four blind cases remain separate evidence of diagnostic transfer.

## Model name and identity separation

The Ollama model name is configuration, not PMM identity.

`ornith:9b` may appear as:

- An Ollama model identifier
- A default model configuration
- A command-line or MCP example

It is not seeded as an identity token or injected as an instruction that the system “is Ornith.” Test identity fixtures use neutral names such as `identity.TestSelf`.

Any future model—including a local model, cloud model, or replacement model—must remain distinct from identities established through PMM’s ledger protocol.

## Verification completed

### Documentation governance verification — 2026-07-20

The Cognitive Charter preservation, `CONTRIBUTING.md` reconciliation, roadmap
re-baseline, and README discoverability update changed documentation only. No
Python file differs from the synchronized `8198e66` base.

Post-change verification recorded:

```text
468 tests passed
git diff --check passed
```

A repository-wide `ruff check .` was also attempted and reported 13 existing
findings in experiment files and `pmm/tests/test_oneshot_cli.py`. A
repository-wide `black --check .` reported that 45 existing Python files would
be reformatted and also emitted a Python 3.14/3.15 parser-version warning. Those
files are unchanged in this documentation branch, so this update does not widen
scope to reformat or repair them. The failures are reported rather than treated
as verification of this documentation change.

### Runtime verification — 2026-07-19

The current code passes:

```text
468 tests passed
git diff --check passed
```

Regression coverage now includes:

- Empty and truncated model output
- Thinking-budget exhaustion before visible output
- Failure isolation from semantic parsing
- Structurally malformed identity claims
- Ordered identity transitions
- Reversed and unanchored identity transitions
- Missing, mixed, duplicate, and future evidence references
- Retrieval reason and score determinism
- Provenance rendering and its non-authority warning
- Typed validation diagnostics
- Optional formal evidence-designation parsing
- Selected and unselected evidence-designation enforcement
- All-or-nothing designation validation
- Natural-language and malformed-header isolation
- Existing-but-unselected `CLAIM evidence_events` rejection
- Prompt telemetry on successful and failed generations
- Prompt-content privacy and backward-compatible diagnostics
- Exact single-primer composition for Ollama, OpenAI, and custom adapters
- Unchanged provider input except for removal of the duplicate primer
- Protocol-v1 user/outcome linkage and terminal uniqueness
- Active transport-error isolation and safe exception telemetry
- Narrow latest-turn interruption recovery and legacy-ledger preservation
- Concurrent SQLite recovery idempotence
- Provider-capability enforcement before managed-turn mutation
- Ollama `num_predict` and OpenAI `max_completion_tokens` mapping
- Conservative output and reasoning-token telemetry
- Length-limited partial-response semantic isolation
- CLI, environment, and MCP output-budget precedence
- Model-name and identity neutrality
- Authoritative commitment-close target, source, idempotence, and reconstructed relationship
- Shared MemeGraph reconstruction and atomic snapshot-to-listener handoff
- Managed-pair graph indexing, exact two-record dereference, bounded non-evidentiary rendering, and evidence separation
- Fenced database ownership, fail-fast contention, trigger enforcement, and transactional hash-chain predecessor selection
- Independent heartbeat, ownership-loss rejection, lease expiry, takeover, and recovery exclusion
- Fixed-watermark required-projection replay, durable health reporting, and typed post-commit failure
- One-shot and MCP contention through the database-scoped authority

The final focused Stage 3 audit suite recorded:

```text
43 tests passed
```

Its coverage included ownership, insert-trigger enforcement, hash-fork prevention, heartbeat, lease loss, expiry and takeover, stale-result rejection, recovery exclusion, projection barriers, required-listener failure, one-shot contention, and MCP contention. Stage 3 verification also recorded Ruff check and Ruff format check across its 24-file Python verification scope, plus `compileall` and diff checks. Publication completed at `69cbe30d49d817afb8cc1fdf1fdee4865a2f586f`; local `main`, `HEAD`, and `origin/main` were clean and synchronized at divergence `0 0`.

For this documentation-only accuracy pass, the complete suite was rerun from the published revision with only this document modified: `.venv/bin/pytest -q` passed 468 tests in 21.35 seconds. This rerun is separate from the recorded Stage 3 publication verification above.

### Integrity-audit and development-control verification — 2026-07-18

A focused audit suite covering identity adoption, identity-claim structure, claim evidence, validation failures, MemeGraph edges, concept schemas and projection, concept compilation, and evidence designations passed:

```text
108 tests passed
```

Those tests corroborate behavior on their exercised paths. The audit also inspected the production control flow and confirmed the narrower boundaries now stated in this document: identity anchors are temporally but not relationally constrained; evidence validation is conditional on declaration; ratification evidence is structurally forbidden; unresolved reflection targets silently omit `reflects_on`; unknown claim types fail open; and validator-rejected extracted claims are preserved without canonical promotion.

The development-auditor package passes structural validation and fresh-prompt discovery. Its four blind diagnostic cases also passed against the preceding draft, demonstrating transfer across coverage, referential enforcement, relational-role, and preservation-versus-promotion failures.

The later repository-state and post-change-reporting requirements were exercised in the real C01 and C02 audit → authorization → implementation → post-change re-audit → publication cycles. This operational evidence is distinct from the four earlier blind diagnostic cases and does not make those earlier cases evidence for requirements they predated.

## Cognitive-lifecycle re-baseline

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

The current production architecture does not yet enforce or reliably preserve
that complete lifecycle as a first-class mechanism. It contains substantial
supporting infrastructure and some informal or partial instances of the
intended stages.

| Cognitive stage or support layer | Current strongest classification |
|---|---|
| Historical preservation and canonical governance | Strong supporting foundation within the audited scopes |
| Model-visible experience reconstruction | Partial; messages and selections are recorded, but the complete experience is not one canonical first-class record |
| Interpretation | May survive within model utterances; missing as a governed first-class lifecycle |
| Reflection | Semantically overloaded across model-authored material, deterministic summaries, maintenance, and diagnostics |
| Meta-reflection | Current pattern summaries do not implement interpretation of interpretation |
| Self-model and identity | Deterministic telemetry and procedural token adoption provide partial infrastructure, not complete semantic revision |
| Ontology revision | Concept topology exists; governed ontology revision is incomplete |
| Commitment and outcome | Lifecycle machinery exists; the required links to interpreted self-state and later review are incomplete |
| Autonomy and self-governance | Operational scheduling and maintenance exist; reflective self-governance is not established |
| Diagnostics, telemetry, summaries, and maintenance | Substantial infrastructure whose isolation from cognition is incomplete |

These classifications are audit findings, not selected implementation changes.
No event vocabulary, schema, migration, rename, remediation order, or historical
reinterpretation is approved by this re-baseline.

The following work remains frozen until separately authorized after governance
reconciliation:

- R17 implementation;
- the reference-policy matrix;
- R06 and R07 enforcement;
- new identity, reflection, ontology, commitment, or other cognitive semantics;
- event-vocabulary and schema selection;
- component renaming;
- historical ledger migration or reinterpretation;
- runtime remediation inferred from the charter.

## Unselected and frozen work candidates

These items remain unimplemented or separately unauthorized. Their document
order is not a priority or remediation sequence. C01, C02 stages 1–3,
managed-writer exclusion, fixed-watermark projection freshness, and
required-listener failure handling remain closed and are not reopened by the
cognitive re-baseline.

The first three candidates retain the earlier distinction among reference
coverage, deterministic relationship checks, and semantic warrant. They are not
authorized for implementation.

### Reference-policy matrix and validator coverage

Inventory every structured claim type, reference-bearing field, producer, validation call site, consumer, projection, and promotion path before changing defaults. For each structure, the policy matrix must decide:

- Whether the reference field is forbidden, optional, or required
- Whether an empty reference collection is meaningful
- Whether each target must exist and have been available to the producing turn
- Whether the structure explicitly distinguishes asserting actor or origin, subject, predicate or relationship type, object or target, and supporting event IDs
- Whether confidence, status, or promotion state exists at all; those fields require separate authorization rather than being inferred from a source label or event kind
- What historical form remains after rejection
- Whether a rejected or unsupported candidate may become a canonical event
- Which projections or authoritative state may consume it

This inventory must account for current behavior that could otherwise be mistaken for a guarantee:

- `evidence_events` may be omitted for every current claim type. Where the field is accepted, the general validator permits an empty list; `identity_ratify` forbids the field entirely.
- `identity_ratify` forbids evidence rather than merely making it optional.
- Unknown structured claim types return `ACCEPTED_UNKNOWN_TYPE` and are promoted to canonical `claim` events with CTL bindings. Reject-by-default must not ship before inventorying behavior that relies on this fallback.
- Current registered identity claims contain a token, optional proposal description, and optional proposal evidence; they do not distinguish a producing or asserting actor from the subject of the assertion. Unknown claim payloads can preserve arbitrary fields, but PMM has no registered relational-claim policy that validates those fields or gives them uniform projected meaning.
- `about_event` is optional for reflection producers; an unresolved target silently produces no `reflects_on` edge.
- The standalone concept schema only type-checks `supersedes`, while the production compiler does not invoke that validator. `ConceptGraph` projects any truthy supplied value without checking target existence, prior-version status, token membership, ordering, or cycle safety.

The general rule is: **“does the referenced thing exist?” belongs to referential validation; “is it permitted in this role?” belongs to relational integrity.** Closing field optionality without specifying role policy would address only part of the problem.

### Deterministic relational integrity

Once the policy matrix exists, add explicit role-bearing relations where one overloaded or optional pointer cannot express the lifecycle. A reinterpretation, for example, may need to distinguish the prior interpretation from the event that triggered revision. An identity transition may need distinct proposal, anchor, trigger, evidence, and ratification roles.

The same inventory must distinguish the asserting actor or origin from the assertion's subject, predicate or relationship type, and object or target, while retaining supporting event IDs. Commitment lifecycle metadata provides a limited implementation precedent: `meta.origin` is constrained to `user`, `assistant`, or `autonomy_kernel` on commitment events. That convention is not proof that origin alone is sufficient for general relational assertions, and it does not select a final schema.

A user assertion about the user must not be promoted into the agent's self-directed identity-adoption path merely because identity adoption is the only currently available durable identity primitive.

> Granite's creator-role error exposed both a model interpretation failure and a representational gap. The ledger currently lacks a sufficiently explicit structure for third-party or user-directed relational assertions, so role-correct promotion cannot be enforced uniformly.

The error is an observed runtime symptom rather than implementation proof. Production code confirms the representational boundary: the registered identity path cannot validate the distinct roles in `asserting actor: Scott`, `subject: Scott`, `predicate: creator_of`, and `object: PMM`. It does not establish why the model made the interpretation error.

An illustrative, not-yet-adopted shape is `proposal_event_id`, `anchor_event_id`, `trigger_event_ids[]`, and `evidence_events[]`, supplemented by role-tagged relations when one event participates in more than one function. The same audit must determine whether flat evidence lists can identify which part of a compound assertion each event supports.

Candidate deterministic checks include:

- Target event or concept kind
- Strict ordering
- Same identity token, CID, concept token, or version history
- Required typed-edge membership
- Binding attribution and origin
- Role cardinality
- Cycle and supersession constraints

These checks can establish that the agent explicitly declared a structurally possible relationship. They do not require another model to judge content. The exact roles, cardinalities, authoritative graph edges, and policy for unsupported proposals remain design decisions and must not be chosen incidentally while patching a validator.

### Semantic adequacy

After referential and relational integrity, the remaining question is whether the cited content genuinely supports the claim, whether the anchor meaningfully concerns the proposed identity, or whether a revision trigger actually warrants the new interpretation.

This is the open frontier. A typed edge proves a declared role, not semantic warrant. PMM should not quietly make an unverified second model judgment authoritative. Possible future work may use explicit typed assertions, corroborating evidence, deterministic contradiction checks, or separately recorded adjudication, but no such policy is currently approved.

### Multiple-identity conflict and replacement policy

PMM currently permits different identity tokens to accumulate if each independently completes the adoption protocol.

A future policy must decide whether identities are:

- Concurrent roles
- Historical versions
- Aliases
- Mutually exclusive replacements
- Members of another explicitly modeled relationship

The system should not assume that two identity tokens necessarily conflict.

### Coherence gating for identity adoption

The coherence subsystem currently records conflicts but does not gate adoption. Identity-token claims also do not naturally enter the existing `domain`/`value` coherence representation.

Before gating adoption, PMM needs a precise answer to:

- Which conflicts are blocking?
- Is coherence advisory or transactional?
- Can a low score prevent state mutation?
- How can a blocked transition later be reconciled?

### Zero-configuration output budget

Explicit provider-neutral output budgets are implemented, but the default remains unset. Define a deterministic automatic budget for capable built-in adapters, keep explicit CLI, MCP, and environment values as advanced overrides, and preserve the current pre-mutation capability check for unsupported adapters.

Context-window budgeting, automatic budget increases, retry behavior, and partial-response acceptance remain separate decisions.

### Controlled generation retry policy

PMM records `generation_failure` but does not retry automatically.

A bounded retry design would need to specify:

- Which statuses are retryable
- Maximum attempts
- Whether token limits may change
- How every attempt is recorded
- How duplicate semantic effects are prevented
- What the caller receives after exhaustion

Retries must never conceal the original failed attempt or allow a partial response to reach semantic parsers.

### Retrieval verification validity and diagnostic isolation

The current autonomy verification path may compare a concept- and topology-influenced hybrid retrieval result against a separately recomputed pure-vector baseline. A disagreement can therefore be expected by design rather than evidence that final retrieval was incorrect.

`AutonomyKernel._verify_recent_selections()` re-ranks message candidates using the configured deterministic embedding model, then asks only whether at least one of its five highest vector matches appears in each final hybrid `retrieval_selection`. The recorded selection may instead contain events admitted or prioritized through forced or sticky concepts, concept bindings, summary handling, thread or graph expansion, topology roots or tails, and vector refinement over a narrower concept-derived candidate set. The verifier does not reproduce those stages or use the recorded per-event reasons when deciding validity. Each autonomy decision cycle that reaches the maintenance block examines up to the same five trailing selections and appends another `reflection`, so overlapping cycles can repeat the same outcome without a per-selection watermark.

Future policy must distinguish at least:

- **Vector-subsystem verification:** compare only vector-ranked candidates and scores under the vector stage's actual candidate set.
- **Full hybrid reproducibility:** rerun the actual retrieval pipeline using the original configuration, inputs, graph state, concept state, and selection boundary.
- **Verification scheduling:** verify each `retrieval_selection` once using a watermark or processed-selection ID instead of repeatedly checking overlapping trailing windows.
- **Diagnostic preservation:** record retrieval verification in a dedicated diagnostic form rather than narrative `reflection`, unless the event genuinely represents reflective interpretation.

Relabeling the event alone would not fix an invalid baseline. Repeated false-positive diagnostics can pollute later retrieval and reflection analysis. No correction is currently authorized or implemented.

### Forced-concept retrieval relevance and attractor control

The audited mechanism is narrower than a general privileged-prefix attractor. `RuntimeLoop.run_turn()` creates a new `RetrievalConfig` for each turn, so that configuration object's `sticky_concepts` does not accumulate indefinitely across the session. `force_concept_prefixes` defaults to `identity.`, `role.`, `policy.`, `commitment.`, and `governance.`, but it filters only concepts already seeded for the turn; it does not scan and inject every matching concept in `ConceptGraph`. The unconditional default seed is `user.identity`, which is handled by a separate force rule as well as the sticky path. Other privileged concepts become forced only when they are seeded through query matching or explicit configuration.

Once seeded, a privileged concept's bound events are force-included without an additional relevance check, and concept-kind topology can add root or tail events to the same forced bucket. Concept and CID bindings can also expand commitment threads and neighboring graph events. Model-emitted first-line `concepts` headers bind the current user and assistant events. If an assistant event carries `meta.concept_ops`, the production compiler can also define and bind concepts from that metadata. Those durable bindings become later retrieval entry points only when the concept is seeded again. Thus a concept such as `governance.risk` or `governance.criterion` could repeatedly reintroduce historical material if it is repeatedly reseeded, but the current production path does not establish that every such concept is injected on every turn.

A conditional feedback loop remains a plausible, not yet causally established, mechanism:

```text
model emits governance or identity concept
  -> concept becomes bound
  -> default or later query/configuration reseeds the concept
  -> forced retrieval injects its events and topology
  -> model sees the same frame as dominant context
  -> model emits or reinforces the concept again
```

Future policy must decide which concepts are universally mandatory, which require query relevance, whether mandatory concepts receive a bounded budget, whether topology expansion applies to every forced concept, and whether force inclusion needs recency, role, state, or lifecycle gating. It must also specify how closed, failed, superseded, or historical commitments influence forced context and how narrative concentration is detected without treating repetition itself as failure. Simple decay is not established as the required solution. No relevance correction or attractor-control policy is currently authorized or implemented.

### Operational baseline for prompt growth

The measurement mechanism is implemented. Before adding prompt-reduction behavior, PMM should run a fresh representative 10–20 turn conversation and observe:

- Prompt-token growth by turn
- Rendered PMM-context size
- Provenance and raw-evidence size
- Selected-event count
- Retrieval-reason concentration by turn, including the count and proportion of `forced_concept`, `sticky_concept`, `concept_binding`, topology or graph expansion, and `vector_refinement` selections
- Repeated event IDs and repeated concept tokens across turns
- Whether query-unrelated forced concepts dominate the rendered context
- Model-response similarity and repeated self-model language
- Resulting concept definitions and event or thread bindings
- Commitments or reflections created from repeatedly injected context
- Output-token count
- Control markers, resulting ledger mutations, binding attribution, relational content, and later utility

The baseline should distinguish prompt-size growth, retrieval concentration, narrative attractors, and semantic usefulness. Current provenance records generic `graph_expansion`, while concept root or tail additions share the `forced_concept` bucket; a future experiment must identify that observability limit rather than pretending those mechanisms are already separable. This baseline is an experiment, not a code change. It should identify whether prompt growth is operationally significant and which component is associated with it. A later controlled behavioral experiment would be required to test causal explanations or determine whether provenance scores improve model self-correction; telemetry alone cannot establish either claim.

## MCP bridge and its use in this cycle

PMM exposes a local STDIO Model Context Protocol server through `pmm.runtime.mcp_server`. The server provides a `pmm_turn` tool that allows an MCP-compatible coding agent such as Codex to submit a prompt to a selected model operating through PMM and receive the structured result of one complete ledger-backed turn.

The bridge invokes PMM's non-interactive one-shot runtime against the database configured by `PMM_MCP_DB`. The selected model is supplied explicitly or taken from `PMM_MCP_MODEL`. Each call passes through PMM's normal retrieval, context rendering, model generation, event writing, claim validation, commitment handling, reflection, identity processing, and diagnostic pipeline.

The structured result can include:

- Visible and raw assistant output
- Generation status and generation-failure diagnostics
- Exact event range appended by the turn
- Opened and closed commitment IDs
- Validated claims
- Typed validation failures
- Identity and summary updates
- Full appended events when `include_events` is enabled

The MCP server retains a non-blocking process-local admission gate and rejects overlapping calls in that process. Database-scoped fenced ownership is authoritative: separate MCP subprocesses, one-shot processes, and other governed writers cannot overlap against the same database. A contender acquires only after clean release or lease expiry, or fails explicitly; no automatic queue, hidden wait, or retry is implied. The one-shot context manager releases ownership deterministically, and the runtime establishes required-projection barriers before graph-dependent managed work.

During this development cycle, Codex used `pmm_turn` to conduct the 30-turn PMM conversation and to consult the model operating inside the PMM pipeline about immediate operational improvements. The model reported friction from the bounded ledger state and projections it received. Codex then inspected the repository, corrected assumptions that did not match the implementation, implemented narrowly scoped patches, and ran focused and full regression suites. The PMM consultations and their resulting state changes were appended to the persistent ledger and became available to later turns.

External advisory consultations used a separate path. Codex invoked `gemma4:cloud` directly through Ollama and supplied an implementation summary. That model ranked candidate improvements and proposed acceptance criteria, but it did not execute a PMM turn or write through the MCP bridge.

The two consultation paths are therefore:

```text
PMM-connected consultation:
Codex → MCP pmm_turn → PMM one-shot runtime → configured model → persistent ledger

External consultation:
Codex → Ollama gemma4:cloud with an implementation summary
```

This bridge enabled a model-consultant-to-coding-agent feedback loop without manually copying PMM output between programs. The PMM-connected model identified operational problems from within the state it could actually observe; Codex translated those reports into implementation changes; and MCP returned structured, ledger-grounded results that could be checked against the source and tests.

## Development audit and model consultation

### Consultation roles

Future consultations should distinguish three roles.

#### Model operating through PMM

The currently configured model should report operational friction from within the PMM context it actually receives. It is best positioned to identify:

- Missing or misleading context
- Retrieval confusion
- State-transition feedback it cannot interpret
- Diagnostic information that would help it correct itself
- Places where PMM instructions conflict with observable ledger evidence

Its report is experiential and operational feedback. It is not proof that its architectural interpretation is correct.

The configured model name must not be treated as its identity. Any identity promoted through the manager-produced adoption path must pass the normal ledger-backed identity protocol; unsupported or unpromoted identity language may still remain in utterance history.

#### External advisory model

An external model such as `gemma4:cloud` can review implementation summaries without participating in the PMM ledger state. It is useful for:

- Ranking engineering risks
- Challenging proposed invariants
- Suggesting acceptance tests
- Identifying contradictions in a patch design
- Comparing integrity benefit against implementation cost

Its recommendations must be translated to the actual PMM schema and source code. For example, prior consultations suggested field names and failure behavior that did not exactly match the implementation; source review corrected those details.

#### Codex with repository-scoped development audit

Codex should use `$pmm-development-auditor` as the implementation and verification discipline:

- Record the active revision and relevant working-tree state
- State the claimed guarantee narrowly enough to falsify
- Trace production, validation, rejection, preservation, canonical recording, projection, retrieval, and promotion
- Find alternate producers, consumers, omission paths, fail-open defaults, and silent degradation
- Separate coverage from enforcement and existence from permitted-role membership
- Identify where model and documentation assumptions differ from production code
- Reduce recommendations to one bounded patch
- Preserve backward compatibility where intentional
- Retrace all affected paths after implementation
- Run focused and appropriate broader tests without treating them as proof of uninspected coverage
- Report the strongest supported conclusion and every verification not performed

### Recommended consultation cycle

Each future improvement should use this sequence:

1. Establish the repository revision and working-tree state being evaluated.
2. State one falsifiable guarantee and trace its complete production-to-promotion lifecycle.
3. Use PMM-connected or external models, when useful, to surface operational examples, risks, and candidate tests; treat their output as hypotheses.
4. Audit every relevant source path and active schema before accepting those hypotheses.
5. Classify coverage, enforcement, referential, relational, semantic, and governance boundaries; identify any policy decision the repository does not settle.
6. Define one bounded invariant and explicit deferrals, then obtain authorization for any unsettled policy choice.
7. Implement only that patch, retrace every affected lifecycle path, and run focused plus appropriate broader tests.
8. Record the scoped result and, when the issue was experiential, ask the PMM-connected model whether the observable problem improved.

### Suggested questions for the next PMM consultation

The next model operating through PMM should be asked:

1. Does retrieval provenance help distinguish relevant memories from authoritative evidence?
2. Are validation failures visible enough to support correction on the next turn?
3. Which current identity or evidence rule causes the most concrete operational confusion?
4. Can it identify a case where an existing event was cited in a role that the ledger does not establish?
5. Can it identify a separate case where an established relationship still does not semantically support the claim?
6. Would a retry after truncation help, or could it create continuity and duplication problems?
7. Which single small change would provide the most immediate improvement now?

The consultation prompt should require the model to distinguish:

- Directly visible ledger evidence
- Rendered PMM state
- Inference about architecture
- Unverified interpretation or proposed policy

## Recommended next decision

The documentation governance reconciliation is the only selected work in this
update. It preserves the Cognitive Charter, aligns `CONTRIBUTING.md`, and
re-baselines this roadmap. It stops before runtime selection.

No next implementation is selected or authorized. R17, the reference-policy
matrix, R06, R07, new cognitive semantics, migrations, renames, and every other
candidate above remain frozen. Their position in this document does not imply
priority.

Any later authorization must begin from the Cognitive Charter and retain the
development-audit sequence already exercised by C01 and C02: establish a clean
revision and falsifiable guarantee, trace production and alternate paths before
change, preserve explicit policy boundaries, retrace the affected lifecycle
afterward, run verification proportionate to risk, and review the exact
publication scope.

The strong substrate remains part of the intended PMM architecture: canonical
write governance, hash-chain protection, projection reconstruction and
freshness, retrieval provenance, graph-guided continuity, typed relationships,
and commitment lifecycle. The re-baseline does not discard or reopen those
scoped accomplishments. It restores the cognitive lifecycle they exist to
support as the governing direction for future decisions.
