# PMM System Guide

This guide describes Persistent Mind Model as implemented on the current
documentation baseline. Current production code remains authoritative if this
guide and the repository diverge.

## System model

PMM wraps model generation with a persistent event ledger and deterministic
runtime services:

```text
EventLog
  -> required projections: Mirror, MemeGraph, ConceptGraph
  -> bounded retrieval and context rendering
  -> model adapter
  -> preserved result or explicit failure
  -> structured extraction, validation, and governed writes
```

The language model generates text. PMM records that text, reconstructs selected
state from prior events, and governs specific structured consequences. PMM does
not treat fluent self-description as proof of identity, correctness, or semantic
warrant.

## Canonical history and writer governance

`pmm/core/event_log.py` stores canonical events in SQLite. Events include a
hash-linked predecessor and content digest so chain integrity can be checked.

Managed writers acquire database-scoped ownership with a fencing token.
Canonical predecessor selection and guarded inserts occur inside the write
transaction. Competing managed writers do not silently share authority.

Some generic append calls route into specialized transactional boundaries. In
particular, commitment opens and closes and vector-overlap diagnostics receive
additional lifecycle validation. A governed append path is not equivalent to
uniform schema or semantic validation for every event kind.

## Required projections

`RuntimeLoop` registers three required projections before graph-dependent work:

- `Mirror` provides fast operational state such as open commitments and
  staleness.
- `MemeGraph` reconstructs selected event relationships and managed-turn links.
- `ConceptGraph` reconstructs concepts, aliases, relations, and bindings.

Each projection is rebuilt from canonical history and registered for incremental
delivery while the EventLog prevents a gap between replay and observation. A
fixed-watermark projection barrier confirms required projections are caught up.
Required rebuild or delivery failure is explicit and fail-closed for managed
operation.

The projections are authoritative only within their declared mechanisms. A
graph edge records a relationship established or inferred by code; it does not
prove semantic adequacy.

## One managed turn

The primary production path is `RuntimeLoop.run_turn` in
`pmm/runtime/loop.py`.

1. PMM appends the managed `user_message`.
2. Required projections are brought through the current canonical watermark.
3. The retrieval pipeline selects bounded prior context.
4. PMM renders retrieval, projected state, and one prior completed managed pair.
5. The adapter receives the system prompt and current user prompt.
6. A complete generation becomes the turn's `assistant_message`; an incomplete
   or failed generation becomes a linked `generation_failure`.
7. PMM records retrieval and turn diagnostics.
8. Exact-prefix parsers inspect the already-preserved assistant output for
   commitments, closures, claims, reflections, and concept controls.
9. Accepted structured effects append new canonical events; rejected extracted
   claims can append typed validation failures.
10. Required projections consume the resulting events.

The prior completed managed pair is conversational context, not evidence. Its
IDs are not added to claim evidence availability or retrieval selection merely
because the pair is rendered.

## Generation results

Adapters return a provider-neutral result with visible text and a status of
`complete`, `empty`, `truncated`, or `indeterminate`.

Only a complete generation can become an `assistant_message` and reach semantic
parsers. Other statuses produce `generation_failure`. Partial visible output may
remain in the failure record, but it cannot create commitments, claims,
closures, identity transitions, or concept operations.

The application-level default output budget is 2,048 tokens for built-in
provider adapters. An explicit argument or `PMM_OUTPUT_BUDGET_TOKENS` overrides
that default. Unsupported custom adapters fail before canonical turn mutation
when an enforced budget cannot be honored.

## Retrieval

`pmm/retrieval/pipeline.py` combines several bounded mechanisms:

- concepts seeded from the current event or configuration;
- events and CIDs bound through `ConceptGraph`;
- current commitment episodes;
- independently triggered historical commitment episodes;
- graph-neighbor expansion;
- lifetime-memory records and summary search;
- optional vector refinement using the configured deterministic hash embedding.

The result stores selected event IDs, relevant CIDs, active concepts, per-event
reason tags, applicable scores, commitment-episode selection metadata, and the
embedding parameters actually used by vector stages.

Concept-to-CID retrieval selects the current episode by default. A historical
episode is expanded only when an independently selected base event belongs to
that exact reconstructed episode, and historical episode count and event count
have separate caps. Current and historical episodes render separately.

Selection provenance explains mechanics. It does not establish that a selected
event is true, authoritative, or semantically sufficient evidence.

## Commitments

Assistant commitments use exact `COMMIT:` lines. The CID is derived from the
commitment text, while each canonical opening remains a distinct historical act.

On governed EventLog paths:

- one CID can have at most one active open;
- repeating an already active commitment reuses the existing open rather than
  creating a second one;
- a close allows a later reopen;
- a new assistant-produced open records and validates the exact originating
  assistant event;
- a close records the exact open event it transitions from;
- an assistant-produced close records and validates the assistant event that
  emitted the matching `CLOSE:<cid>` line.

`MemeGraph` reconstructs each open-to-close `CommitmentEpisode`, exposes the
ordered history for a CID, and preserves whether opening and closing origins are
explicit, legacy-inferred, absent, or invalid. Legacy history remains immutable.

This establishes bounded lifecycle and provenance integrity. It does not prove
that two episodes are semantically the same obligation or that closure text
constitutes genuine fulfillment.

## Claims and evidence

Assistant output can contain `CLAIM:type=JSON` lines. The runtime validates
successfully extracted candidates before appending canonical `claim` events.
Rejected candidates can produce `validation_failure` events while the original
assistant utterance remains in history.

Current limits:

- `evidence_events` can be omitted;
- declared evidence IDs must exist, and the managed runtime also requires them
  to have been selected for the turn;
- existence and selection do not prove that an event is permitted or adequate
  for the claimed role;
- `identity_ratify` currently forbids evidence fields;
- unknown structured claim types currently pass through an
  `ACCEPTED_UNKNOWN_TYPE` compatibility path.

Malformed exact-prefix JSON may remain only in utterance history because it can
fail before a typed claim candidate exists.

## Identity adoption

The current identity manager recognizes validated `identity_proposal` and
`identity_ratify` claims with the same token. Adoption requires a later
reflection or commitment lifecycle event between proposal and ratification.

That mechanism enforces temporal order for manager-produced adoption. It does
not establish that the intervening event is relevant to the identity proposal,
and the registered claim structure does not fully distinguish asserting actor,
subject, predicate, object, and supporting roles.

## Concepts and bindings

`ConceptGraph` consumes concept definitions, aliases, relations, event bindings,
and CID-thread bindings. Bindings retain attribution such as operator-declared,
model-declared, runtime-derived, or legacy-unknown origin when available.

The production concept-operations compiler can define and bind concepts from
structured assistant metadata. Current supersession handling is not a complete
ledger-aware version policy: some paths type-check a supplied identifier without
uniformly enforcing existence, same-token history, ordering, or cycle safety.

## Reflections, summaries, and self-model signals

PMM records several structures that have historically shared reflection-like
language. Their mechanisms must remain distinct:

- model-authored reflection content is preserved model output;
- deterministic synthesized reflections summarize bounded runtime deltas;
- governed outcome reviews may receive later governed reinterpretations through
  one exact `reinterprets` relationship, without rewriting the review;
- lifetime memory compresses older spans while retaining representative handles;
- the Recursive Self-Model derives bounded counters and lexical signals;
- diagnostics and maintenance report operational behavior.

These mechanisms can support later interpretation. They do not themselves prove
deep semantic introspection or reflective self-governance.

`reflection_reinterpretation.v1` is deliberately not a general reflection
framework. Its only eligible target is an exact authoritative
`commitment_outcome_review.v1`; ordinary reflections and reinterpretations are
not eligible targets.

## Autonomy

The one-shot and MCP paths construct `RuntimeLoop` with the background autonomy
supervisor disabled. Interactive or explicitly configured runtimes may enable
scheduled autonomy. Autonomous mutations still use governed EventLog paths and
the same required projections.

Scheduling maintenance is operational autonomy. The full charter lifecycle from
interpretation through later reinterpretation is not yet a mandatory
first-class mechanism.

## Entry points

After installation:

```bash
pmm
pmm-turn --db ./pmm.db --provider dummy --prompt "Hello"
```

The equivalent modules are:

```bash
.venv/bin/python -m pmm.runtime.cli
.venv/bin/python -m pmm.runtime.oneshot_cli --db ./pmm.db --provider dummy --prompt "Hello"
```

The STDIO MCP server is:

```bash
PMM_MCP_DB=/absolute/path/to/pmm.db \
.venv/bin/python -m pmm.runtime.mcp_server
```

`PMM_MCP_DB` is required. `PMM_MCP_MODEL` selects the default model for MCP
turns. Calls against one database must remain serialized.

## Strongest current boundary

PMM has a strong persistence, writer-governance, projection, commitment, and
retrieval substrate within audited managed-runtime paths. General reference
coverage and role enforcement remain uneven, and semantic adequacy remains
unresolved.

The next project task is recorded in the
[Current Status and Roadmap](../pmm-improvement-progress.md).
