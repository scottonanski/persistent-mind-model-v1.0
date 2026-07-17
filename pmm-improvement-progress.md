# PMM Improvement Progress and Remaining Work

**Status date:** 2026-07-17  
**Current verification:** 390 tests passing; `git diff --check` passing
**Scope:** Incremental integrity, continuity, diagnostics, and retrieval improvements developed through model consultation and source-level review.

## Purpose

This document records the PMM improvements completed during the current development cycle, the invariants they establish, the work still under consideration, and the process for further consultation with models operating both outside and inside PMM.

The work follows one rule: implement one small, observable, testable change at a time. Model recommendations are treated as operational feedback and design input, not as authoritative specifications. Each recommendation is checked against the source code before implementation.

## Current status

The two model-generated roadmaps used during this cycle are complete. Eight related improvements have been implemented. The evidence-availability branch is complete, and prompt-growth telemetry is the next planned area.

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

> PMM verifies that formally designated evidence existed and was selected for the current turn. It does not determine whether that evidence proves or semantically supports the associated assertion.

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

The isolated final ledger created no commitments or identity mutations. These results confirm availability enforcement, all-or-nothing behavior, prose isolation, and auditable failure linkage.

Explicit semantic limitation:

> Selection proves only that the model received the event in its rendered context. PMM does not yet prove that event 17 truly supports `selected_seed`, nor does it infer evidentiary meaning from unrestricted natural language.

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
390 tests passed
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
- Model-name and identity neutrality

## Remaining backlog candidates

These items remain unimplemented. Prompt-growth telemetry is next in the planned sequence; the other candidates remain unapproved and unordered.

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

### 6. Operational monitoring of prompt growth

Rendering retrieval provenance adds useful context but consumes tokens. PMM should measure:

- Provenance-section size
- Total prompt-token growth
- Whether verbose multi-reason records displace useful evidence
- Whether scores measurably improve model self-correction

This should begin as telemetry, not premature truncation logic.

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

The formal evidence-availability branch is complete. Do not begin semantic grounding or identity conflict policy automatically. The next planned area is operational monitoring of prompt growth.

Begin with telemetry only: measure the rendered retrieval-provenance section size, total prompt-token growth, evidence displacement risk, and whether provenance scores measurably improve correction behavior. Do not add truncation policy until the measurements justify one.

The current system has stronger transport integrity, claim integrity, identity-transition ordering, evidence referential integrity, evidence-availability enforcement, retrieval auditability, and diagnostic visibility than it had at the start of this cycle. Semantic support remains explicitly unresolved: availability is auditable, but entailment is not.
