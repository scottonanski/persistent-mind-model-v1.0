# PMM Improvement Progress and Remaining Work

**Status date:** 2026-07-17  
**Current verification:** 417 tests passing; `git diff --check` passing
**Scope:** Incremental integrity, continuity, diagnostics, and retrieval improvements developed through model consultation and source-level review.

## Purpose

This document records the PMM improvements completed during the current development cycle, the invariants they establish, the work still under consideration, and the process for further consultation with models operating both outside and inside PMM.

The work follows one rule: implement one small, observable, testable change at a time. Model recommendations are treated as operational feedback and design input, not as authoritative specifications. Each recommendation is checked against the source code before implementation.

## Current status

The two model-generated roadmaps used during this cycle are complete. Twelve related improvements have been implemented. The evidence-availability branch, prompt-growth telemetry, duplicate-primer correction, managed-turn terminal-outcome protocol, and provider-enforced output budgets are complete. The next step is ordinary operation and observation rather than another immediate feature.

The remaining items listed later in this document are backlog candidates. They require another consultation and explicit prioritization before implementation.

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

### 2. Structural validation of identity claims

`identity_proposal` and `identity_ratify` no longer pass through the generic “unknown claim type” acceptance path.

Identity claims now require:

- An object-shaped payload
- A non-empty string `token`
- Only supported fields
- A non-empty description when one is supplied
- A structurally valid `evidence_events` list when one is supplied

This closes the original “magic words with parseable JSON” validation hole at the claim-ingress boundary.

### 3. Ordered identity-adoption state machine

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

### 5. Referential validation of evidence events

Any structured claim containing `evidence_events` is now checked against the ledger before the claim is persisted.

Established invariant:

> Claims may cite no evidence, but every event they cite must already exist at validation time.

Behavior:

- Existing IDs are accepted.
- An empty list is accepted.
- Duplicate valid IDs are accepted.
- Any missing ID rejects the complete claim.
- Mixed existing and missing IDs reject the complete claim.
- Boolean, string, zero, negative, and otherwise malformed IDs are rejected.
- A claim cannot cite its own eventual claim-event ID because that event does not exist during validation.

This is referential validation only. PMM confirms that an event exists; it does not yet prove that the event supports the claim.

### 6. Retrieval provenance rendered to the model

The selected model now receives a `Retrieval Selection Mechanics` section showing why each evidence event appeared and any applicable retrieval score.

The section explicitly states:

> These fields explain why an event was selected. They do not establish truth, authority, confidence, or evidence quality. Similarity scores measure retrieval relevance only.

This changes provenance from a ledger-only audit facility into information the model can reason about while preventing a high similarity score from being framed as proof.

### 7. Typed claim-validation diagnostics

Rejected claims now create a canonical `validation_failure` event with:

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

Rejected claims remain excluded from claim persistence, ConceptGraph binding, and identity adoption. Existing narrative reflection behavior remains for compatibility; the typed event is the authoritative diagnostic.

### 8. Formal evidence-availability validation

PMM now distinguishes between an event that exists in the ledger and an event that was actually available to the model during the turn in which it made a formal evidence claim.

Models may emit an optional `evidence_designations` array in the first-line structured JSON header:

```json
{"evidence_designations":[{"event_id":17,"supports":"selected_seed"}]}
```

The field is optional. Its absence means that the response makes no formal evidence designations. Event numbers in ordinary prose remain ordinary prose and are not parsed as evidence claims. Broken first-line JSON is also treated as prose because PMM does not infer structured intent from malformed text.

Established invariant:

> PMM verifies that formally designated event evidence existed and was selected for the current turn's raw-event evidence channel. It does not determine whether that evidence proves or semantically supports the associated assertion.

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

The isolated final ledger created no commitments or identity mutations. That is a recorded outcome of these controlled responses, not an independent success criterion: appropriate commitments can represent valid ontological crystallization in PMM. The results confirm raw-event availability enforcement, all-or-nothing behavior, prose isolation, and auditable failure linkage.

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

## Model name and identity separation

The Ollama model name is configuration, not PMM identity.

`ornith:9b` may appear as:

- An Ollama model identifier
- A default model configuration
- A command-line or MCP example

It is not seeded as an identity token or injected as an instruction that the system “is Ornith.” Test identity fixtures use neutral names such as `identity.TestSelf`.

Any future model—including a local model, cloud model, or replacement model—must remain distinct from identities established through PMM’s ledger protocol.

## Verification completed

The current code passes:

```text
417 tests passed
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

## Remaining backlog candidates

These items remain unimplemented. Prompt-growth telemetry is complete; the other candidates remain unapproved and unordered.

### 1. Semantic grounding of identity anchors and evidence

Current PMM can prove that an anchor or cited event exists, and formal evidence validation can prove that a cited event was selected for the model's current turn. It cannot yet prove that the event is meaningfully related to the proposed identity or that it supports the associated claim.

Open design questions:

- Should semantic support be determined through explicit concept bindings?
- Should evidence require a declared relationship rather than an embedding threshold?
- Can validation remain deterministic without another LLM judgment?
- What false-positive and false-negative behavior is acceptable?

This is the largest conceptual step and should not be implemented as a casual similarity threshold.

### 2. Multiple-identity conflict and replacement policy

PMM currently permits different identity tokens to accumulate if each independently completes the adoption protocol.

A future policy must decide whether identities are:

- Concurrent roles
- Historical versions
- Aliases
- Mutually exclusive replacements
- Members of another explicitly modeled relationship

The system should not assume that two identity tokens necessarily conflict.

### 3. Coherence gating for identity adoption

The coherence subsystem currently records conflicts but does not gate adoption. Identity-token claims also do not naturally enter the existing `domain`/`value` coherence representation.

Before gating adoption, PMM needs a precise answer to:

- Which conflicts are blocking?
- Is coherence advisory or transactional?
- Can a low score prevent state mutation?
- How can a blocked transition later be reconciled?

### 4. Unknown claim-type policy

Unknown non-identity claim types remain accepted for backward compatibility.

Possible future approaches include:

- A registered claim-type schema table
- Reject-by-default behavior for new ledgers
- Compatibility mode for existing deployments
- An explicit generic-claim envelope

This change has migration and ecosystem risks and should not be made globally without an inventory of existing claim types.

### 5. Controlled generation retry policy

PMM records `generation_failure` but does not retry automatically.

A bounded retry design would need to specify:

- Which statuses are retryable
- Maximum attempts
- Whether token limits may change
- How every attempt is recorded
- How duplicate semantic effects are prevented
- What the caller receives after exhaustion

Retries must never conceal the original failed attempt or allow a partial response to reach semantic parsers.

### 6. Operational baseline for prompt growth

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

## Further consultation with models

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

The configured model name must not be treated as its identity. Any identity claim must pass the normal ledger-backed identity protocol.

#### External advisory model

An external model such as `gemma4:cloud` can review implementation summaries without participating in the PMM ledger state. It is useful for:

- Ranking engineering risks
- Challenging proposed invariants
- Suggesting acceptance tests
- Identifying contradictions in a patch design
- Comparing integrity benefit against implementation cost

Its recommendations must be translated to the actual PMM schema and source code. For example, prior consultations suggested field names and failure behavior that did not exactly match the implementation; source review corrected those details.

#### Codex and source-level verification

Codex should serve as the implementation and verification layer:

- Inspect the actual runtime path
- Identify where model assumptions differ from the code
- Reduce recommendations to one bounded patch
- Preserve backward compatibility where intentional
- Write acceptance and regression tests
- Run the complete suite
- Report deviations from the consulting model’s proposal

### Recommended consultation cycle

Each future improvement should use this sequence:

1. Ask the PMM-connected model which current limitation most affects its operation.
2. Require concrete examples grounded in retrieved ledger events or visible PMM context.
3. Ask an external advisory model to rank the issue by integrity benefit and implementation risk.
4. Inspect the source code and active schemas before accepting either model’s assumptions.
5. Define one precise invariant and explicit deferrals.
6. Implement only the bounded patch.
7. Run focused tests and the complete regression suite.
8. Record the result and ask the PMM-connected model whether the observable problem improved.

### Suggested questions for the next PMM consultation

The next model operating through PMM should be asked:

1. Does retrieval provenance help distinguish relevant memories from authoritative evidence?
2. Are validation failures visible enough to support correction on the next turn?
3. Which current identity or evidence rule causes the most concrete operational confusion?
4. Can it identify a case where an existing event was cited but did not actually support the claim?
5. Would a retry after truncation help, or could it create continuity and duplication problems?
6. Which single small change would provide the most immediate improvement now?

The consultation prompt should require the model to distinguish:

- Directly visible ledger evidence
- Rendered PMM state
- Inference about architecture
- Metaphorical or phenomenological language

## Recommended next decision

The formal evidence-availability branch, prompt telemetry, duplicate-primer correction, managed-turn terminal accounting, and provider output budgets are complete. Do not begin semantic grounding, identity conflict policy, retries, or automatic context truncation.

Before further ordinary operation, design a zero-configuration automatic output budget for built-in capable adapters. Keep explicit CLI, MCP, and environment values as advanced overrides rather than normal setup requirements. Keep retries, partial-response acceptance, automatic budget increases, and context-window budgeting deferred.

The current system has stronger transport integrity, claim integrity, identity-transition ordering, evidence referential integrity, evidence-availability enforcement, retrieval auditability, and diagnostic visibility than it had at the start of this cycle. Semantic support remains explicitly unresolved: availability is auditable, but entailment is not.
