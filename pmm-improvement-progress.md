# PMM Improvement Progress and Remaining Work

- **Status date:** 2026-07-18
- **Audit basis:** `main` at `484f55f`, including the current working tree
- **Current verification:** 427 runtime tests passing; `git diff --check` passing; PMM development-auditor package validation and repository discovery passing
- **Scope:** Incremental integrity, continuity, diagnostics, retrieval, and development-audit improvements established through model consultation and source-level verification.

## Purpose

This document records the PMM improvements completed during the current development cycle, the narrow guarantees they establish, the boundaries they do not establish, the work still under consideration, and the process for further consultation with models operating both outside and inside PMM.

The work follows one rule: implement one small, observable, testable change at a time. Model recommendations are treated as operational feedback and design input, not as authoritative specifications. Each recommendation is checked against the source code before implementation.

## Governing architectural and audit lens

PMM is being developed through this lens:

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

This philosophical lens guides questions for the implementation; it does not prove that the implementation answers them. The current production code remains authoritative over research artifacts, documentation, tests, and model descriptions. The deep research report in `docs/deep-research-report.md` is retained as architectural and philosophical source material, not as the governing specification.

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

The two model-generated runtime roadmaps used during this cycle are complete. Twelve related runtime improvements have been implemented. The evidence-availability branch, prompt-growth telemetry, duplicate-primer correction, managed-turn terminal-outcome protocol, and provider-enforced output budgets are complete within the scopes described below.

The subsequent architecture audit did not change runtime code. It clarified the boundary between temporal ordering, referential checks, relational integrity, and semantic adequacy, and produced one repository-scoped development-audit skill plus mandatory agent routing. Those development controls are described separately from the twelve runtime improvements.

The current integrity position is:

| Layer | Strongest supported conclusion |
|---|---|
| Historical preservation | On the audited managed-runtime terminal path, complete assistant utterances are retained. Parsed candidates rejected by the runtime validator also produce distinct `validation_failure` events; they do not produce canonical `claim` events. Malformed claim lines remain in utterance history but may never become extracted candidates or typed failures. |
| Referential validation | Implemented for declared `evidence_events` and formal evidence designations on the audited runtime path, but coverage is conditional and uneven across reference-bearing structures. |
| Deterministic relational integrity | Partially implemented. PMM records useful typed edges and ordering, but identity anchors, reflections, supersessions, and evidence roles do not yet receive uniform permitted-role checks. |
| Semantic adequacy | Unresolved. PMM does not establish that an existing or selected event genuinely supports a claim or warrants an interpretation. |

The relational memory substrate is currently richer than the recursive introspection mechanism. `MemeGraph`, `ConceptGraph`, retrieval provenance, commitments, and event ordering preserve substantial topology. `RecursiveSelfModel` primarily derives bounded counters, lexical-marker tendencies, sliding-window gap signals, hash-prefix uniqueness, and recorded reflection intents. `Mirror` can compare those deterministic projections across time. Together they can establish that recorded patterns changed; they do not yet establish a deep semantic explanation of why an interpretation changed.

The remaining items are a mixture of operational backlog candidates and integrity-policy decisions. Model consultation may generate useful hypotheses, but mechanically specifiable gaps now require repository inventory and explicit policy choices rather than more model consensus.

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

Recovery is intentionally narrow. Runtime initialization examines only the latest user event and recovers it only when it opts into protocol v1, has no linked terminal outcome, and is followed solely by its recognized pre-generation embedding side effect. Ambiguous suffixes and legacy turns remain unchanged. General cross-process serialization remains unresolved; the supported database contract is still one active writer.

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

Repository-state capture and mandatory post-change retracing were added after those blind runs. The current package and prompt-discovery checks establish that those requirements are structurally valid and delivered to compliant agents, but they have not yet been exercised in a blind end-to-end PMM implementation cycle.

## Model name and identity separation

The Ollama model name is configuration, not PMM identity.

`ornith:9b` may appear as:

- An Ollama model identifier
- A default model configuration
- A command-line or MCP example

It is not seeded as an identity token or injected as an instruction that the system “is Ornith.” Test identity fixtures use neutral names such as `identity.TestSelf`.

Any future model—including a local model, cloud model, or replacement model—must remain distinct from identities established through PMM’s ledger protocol.

## Verification completed

### Runtime verification — 2026-07-18

The current code passes:

```text
427 tests passed
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

### Integrity-audit and development-control verification — 2026-07-18

A focused audit suite covering identity adoption, identity-claim structure, claim evidence, validation failures, MemeGraph edges, concept schemas and projection, concept compilation, and evidence designations passed:

```text
108 tests passed
```

Those tests corroborate behavior on their exercised paths. The audit also inspected the production control flow and confirmed the narrower boundaries now stated in this document: identity anchors are temporally but not relationally constrained; evidence validation is conditional on declaration; ratification evidence is structurally forbidden; unresolved reflection targets silently omit `reflects_on`; unknown claim types fail open; and validator-rejected extracted claims are preserved without canonical promotion.

The development-auditor package passes structural validation and fresh-prompt discovery. Its four blind diagnostic cases also passed against the preceding draft, demonstrating transfer across coverage, referential enforcement, relational-role, and preservation-versus-promotion failures.

The later repository-state and post-change-reporting requirements are **structurally validated but not yet blindly exercised in a complete audit → implementation → post-change re-audit cycle**. The passing diagnostic cases should not be represented as validation of requirements they predated.

## Remaining backlog candidates

These items remain unimplemented. The first three replace the former single “semantic grounding” item because reference coverage, deterministic relationship checks, and semantic warrant are different problems.

### 1. Reference-policy matrix and validator coverage

Inventory every structured claim type, reference-bearing field, producer, validation call site, consumer, projection, and promotion path before changing defaults. For each structure, the policy matrix must decide:

- Whether the reference field is forbidden, optional, or required
- Whether an empty reference collection is meaningful
- Whether each target must exist and have been available to the producing turn
- What historical form remains after rejection
- Whether a rejected or unsupported candidate may become a canonical event
- Which projections or authoritative state may consume it

This inventory must account for current behavior that could otherwise be mistaken for a guarantee:

- `evidence_events` may be omitted for every current claim type. Where the field is accepted, the general validator permits an empty list; `identity_ratify` forbids the field entirely.
- `identity_ratify` forbids evidence rather than merely making it optional.
- Unknown structured claim types return `ACCEPTED_UNKNOWN_TYPE` and are promoted to canonical `claim` events with CTL bindings. Reject-by-default must not ship before inventorying behavior that relies on this fallback.
- `about_event` is optional for reflection producers; an unresolved target silently produces no `reflects_on` edge.
- The standalone concept schema only type-checks `supersedes`, while the production compiler does not invoke that validator. `ConceptGraph` projects any truthy supplied value without checking target existence, prior-version status, token membership, ordering, or cycle safety.

The general rule is: **“does the referenced thing exist?” belongs to referential validation; “is it permitted in this role?” belongs to relational integrity.** Closing field optionality without specifying role policy would address only part of the problem.

### 2. Deterministic relational integrity

Once the policy matrix exists, add explicit role-bearing relations where one overloaded or optional pointer cannot express the lifecycle. A reinterpretation, for example, may need to distinguish the prior interpretation from the event that triggered revision. An identity transition may need distinct proposal, anchor, trigger, evidence, and ratification roles.

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

### 3. Semantic adequacy

After referential and relational integrity, the remaining question is whether the cited content genuinely supports the claim, whether the anchor meaningfully concerns the proposed identity, or whether a revision trigger actually warrants the new interpretation.

This is the open frontier. A typed edge proves a declared role, not semantic warrant. PMM should not quietly make an unverified second model judgment authoritative. Possible future work may use explicit typed assertions, corroborating evidence, deterministic contradiction checks, or separately recorded adjudication, but no such policy is currently approved.

### 4. Multiple-identity conflict and replacement policy

PMM currently permits different identity tokens to accumulate if each independently completes the adoption protocol.

A future policy must decide whether identities are:

- Concurrent roles
- Historical versions
- Aliases
- Mutually exclusive replacements
- Members of another explicitly modeled relationship

The system should not assume that two identity tokens necessarily conflict.

### 5. Coherence gating for identity adoption

The coherence subsystem currently records conflicts but does not gate adoption. Identity-token claims also do not naturally enter the existing `domain`/`value` coherence representation.

Before gating adoption, PMM needs a precise answer to:

- Which conflicts are blocking?
- Is coherence advisory or transactional?
- Can a low score prevent state mutation?
- How can a blocked transition later be reconciled?

### 6. Zero-configuration output budget

Explicit provider-neutral output budgets are implemented, but the default remains unset. Define a deterministic automatic budget for capable built-in adapters, keep explicit CLI, MCP, and environment values as advanced overrides, and preserve the current pre-mutation capability check for unsupported adapters.

Context-window budgeting, automatic budget increases, retry behavior, and partial-response acceptance remain separate decisions.

### 7. Controlled generation retry policy

PMM records `generation_failure` but does not retry automatically.

A bounded retry design would need to specify:

- Which statuses are retryable
- Maximum attempts
- Whether token limits may change
- How every attempt is recorded
- How duplicate semantic effects are prevented
- What the caller receives after exhaustion

Retries must never conceal the original failed attempt or allow a partial response to reach semantic parsers.

### 8. Operational baseline for prompt growth

The measurement mechanism is implemented. Before adding prompt-reduction behavior, PMM should run a fresh representative 10–20 turn conversation and observe:

- Prompt-token growth by turn
- Rendered PMM-context size
- Provenance and raw-evidence size
- Selected-event count
- Output-token count
- Control markers, resulting ledger mutations, binding attribution, relational content, and later utility

This baseline is an experiment, not a code change. It should identify whether prompt growth is operationally significant and which component causes it. A later controlled behavioral experiment would be required to determine whether provenance scores improve model self-correction; telemetry alone cannot establish that claim.

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

Calls handled by one MCP server process are serialized by a process-level lock. This prevents two turns routed through that server from overlapping their event ranges. Multiple independent MCP server processes must not be pointed at the same database concurrently unless a stronger cross-process serialization mechanism is added.

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

The next development-control step is to run one real, bounded PMM change through the complete skill lifecycle:

1. Capture the branch, revision, working-tree state, and falsifiable pre-change guarantee.
2. Audit production, validation, preservation, projection, and promotion paths before implementation.
3. Implement one explicitly authorized policy change.
4. Retrace every affected path, run focused and appropriate broader tests, and report omitted verification.
5. Confirm that the final finding format distinguishes the implemented guarantee from remaining weaker paths.

This cycle should exercise the repository-state and post-change requirements added after the successful blind diagnostic cases. Failure in those newer behaviors—not the already-demonstrated diagnostic core—should drive the next skill revision.

The next runtime-integrity step is an inventory, not a patch:

1. Enumerate claim types, reference-bearing fields, producers, validators, consumers, projections, and promotion paths.
2. Record which paths currently rely on optional evidence, token-only ratification, unknown-type fail-open, optional `about_event`, and unvalidated `supersedes` metadata.
3. Draft the explicit policy matrix for omission, emptiness, target existence, selected availability, permitted roles, rejection preservation, and authoritative promotion.
4. Authorize and implement referential coverage and enforcement changes as a separate patch.
5. Specify deterministic role-bearing relations and constraints as a later relational-integrity patch.
6. Keep semantic adequacy explicitly open rather than resolving it through another unverified model gate.

The zero-configuration output budget remains a separate product improvement for built-in capable adapters. Keep explicit CLI, MCP, and environment values as advanced overrides, and keep retries, partial-response acceptance, automatic budget increases, and context-window budgeting deferred.

The current system has stronger transport integrity, temporally ordered identity adoption, conditional evidence referential and availability validation, retrieval auditability, and diagnostic visibility than it had at the start of this cycle. It does not yet establish mandatory evidence coverage, identity-anchor relevance, uniform reflection topology, valid supersession relationships, or semantic support.
