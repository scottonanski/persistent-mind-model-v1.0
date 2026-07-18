# Concept-authorship channel audit

Status: design only. No parser, prompt, attribution, retrieval, or production
behavior change is authorized by this document.

## Motivation and observed result

Two different model families operating through PMM performed relational
discovery that the Concept Token Layer did not record as model-authored
structure:

- Granite proposed `identity.adaptive_continuity` and connected it to strategic
  replacement, preservation, and continuity.
- Gemma developed productive friction, honest witnessing of rupture, relational
  erasure, and traceable continuity across contradiction.

Both models emitted structured JSON during natural conversation. The relevant
objects appeared inside Markdown fences, later in the response, or in exact
`REFLECT:` lines rather than as an unfenced first-line JSON object. The accurate
finding is therefore:

> Models performed relational discovery, but no naturally emitted concept JSON
> appeared in the exact first-line form accepted by the current runtime.

The universal fallback preserved later continuity under
`identity.continuity`, but it did not preserve the discoveries' conceptual
specificity or model authorship. This has now appeared with both Granite and
Gemma and should be treated as a model-to-runtime interface issue rather than a
model-specific quirk.

## Current channel

`RuntimeLoop.run_turn` currently performs these steps:

1. Select only the first response line (or the entire response when it has one
   line).
2. Call `json.loads` on that string.
3. If the result is an object, read optional `concepts` and the structured
   assistant fields `intent`, `outcome`, `next`, and `self_model`.
4. If no concepts survive, apply meditation concepts or the universal
   `identity.continuity` fallback.
5. Persist the assistant event, then bind its active concepts to the current
   user and assistant events and to any commitment opened by that response.
6. Attribute accepted header concepts as `model_declared`, with
   `origin_event_id` identifying the assistant event.

This design gives the parser a small, deterministic surface. It does not scan
prose, guess at concept words, or interpret arbitrary JSON fragments. That is a
real safety property.

The first-line requirement also has costs:

- Markdown fences make the first line `````json`` rather than the object.
- A conversational preamble makes the first line prose.
- A correct later object is ignored.
- A failed header parse discards all model concept authorship for the turn.
- Bindings can name tokens that have no `concept_define`; those associations
  exist in the projection but are not discoverable through the lexical CTL
  injector's defined-token inventory.

The primer contributes an avoidable conflict. It says to speak first as a
conversational being and use structured tools afterward, while its JSON-header
guidance requires the object before the natural-language response. Models have
resolved that tension inconsistently through fences, later blocks, or prose.

## Adjacent structured channels

### Exact line markers

`COMMIT:`, `CLOSE:`, `CLAIM:`, and `REFLECT:` are recognized anywhere in the
response only when the line begins with the exact prefix at column zero. This
has proven more compatible with natural responses because prose can come first
without making the control line ambiguous.

### REFLECT payloads

`REFLECT:` parses the first exact prefixed line whose suffix is a JSON object.
There is no version discriminator or strict key schema at extraction time.
Downstream reflection composition reads only:

- `observations`
- `corrections`
- `next`

Other fields are silently ignored. Gemma naturally used fields such as
`observation`, `insight`, `connection`, and `state`. Those objects parsed, but
their relational content did not become the persisted reflection composed from
the control payload.

Concepts inside an arbitrary current `REFLECT:` object must not automatically
mutate CTL. The current extractor proves only that the suffix is a JSON object;
it does not prove conformance to a concept-declaration schema.

### concept_ops compiler

The repository contains a deterministic compiler for definitions, aliases,
event bindings, and relations. The assistant-event entry point expects
`assistant_message.meta.concept_ops` and correctly attributes compiled bindings
to the assistant event. The ordinary runtime header path does not currently put
parsed `concept_ops` into that metadata, so this compiler is not a general path
from natural model output to CTL operations.

This distinction should remain explicit: labeling the current turn with a few
concept tokens is a smaller authority than defining concepts, aliasing tokens,
relating concepts, or binding arbitrary historical events.

## Threat model

Any broader authorship channel must prevent these cases from mutating CTL:

- JSON shown as an example, quotation, or code sample;
- fenced application data unrelated to PMM;
- prose that happens to contain concept-like dotted identifiers;
- malformed or truncated control output;
- two conflicting declarations in one response;
- unknown keys smuggled into an otherwise plausible object;
- a model binding events it did not receive through the raw evidence channel;
- a model redefining an existing token without an explicit revision operation;
- duplicate replay creating additional effective associations;
- a runtime fallback being reclassified retrospectively as model authorship.

No design should infer declarations by extracting nouns, dotted strings,
Markdown headings, or unrestricted JSON from prose.

## Candidate designs

### A. Accept generic fenced or later JSON

Search the response for JSON objects, including ordinary `````json`` blocks,
and accept any object containing `concepts`.

This would capture the observed Granite formatting, but it is not recommended.
Models routinely use fenced JSON for examples and application data. Location
and the presence of a familiar key do not establish intent to mutate persistent
state. Multiple blocks, nested objects, and truncated fences also create
avoidable ambiguity.

### B. Dedicated versioned control envelope

Permit one exact line at column zero after the conversational response:

```text
PMM-CONTROL:{"schema":"pmm.control.v1","concepts":["identity.adaptive_continuity"]}
```

The prefix expresses mutation intent; the schema discriminator identifies the
contract; the single-line suffix remains ordinary deterministic JSON parsing.
This aligns with the marker channel that both tested model families already use
after prose. Generic JSON and generic Markdown fences remain inert.

For association-only declarations, the accepted authority should be narrow:

- bind accepted tokens to the current user and assistant events;
- bind them to commitments opened by the same assistant event;
- create `model_declared` attribution assertions linked to that assistant event;
- do not define, alias, relate, or bind arbitrary historical events.

### C. Versioned REFLECT concepts

Permit concepts only in a strictly validated reflection envelope, for example:

```text
REFLECT:{"schema":"pmm.reflect.v2","observations":["..."],"concepts":["continuity.productive_friction"]}
```

This is deterministic and semantically attractive when the discovery genuinely
arises from reflection. It should not make every current arbitrary `REFLECT:`
object authoritative. A v2 discriminator, allowed-key schema, canonical concept
rules, and explicit validation outcome are required.

Reflection attribution and concept attribution should remain separate facts:
the assistant event is the origin of the declaration, while any persisted
reflection event is a derived lifecycle record. The concept binding's
`origin_event_id` should continue to identify the assistant event.

### D. Full CTL operation envelope

A separate exact prefix could expose definitions and relations:

```text
PMM-CTL:{"schema":"pmm.ctl_ops.v1","define":[...],"relate":[...]}
```

This is materially more powerful than labeling the current turn. It should not
be bundled casually with association-only concepts. Historical `bind_events`
would need raw-evidence availability validation, and definitions, aliases, and
relations would need strict schemas plus conflict and revision rules.

## Recommended direction

The smallest promising design is **B**, optionally followed later by the
reflection-specific extension in **C**.

Use one provider-neutral, versioned, exact-prefix control line after prose.
Retire the contradictory expectation that model-authored concepts must be both
first-line and subordinate to a conversational response. Do not accept generic
fenced JSON or scan later prose for objects.

Association-only declaration validation should be all-or-nothing:

1. Exactly zero or one `PMM-CONTROL:` line per successful response.
2. Prefix starts at column zero and the payload occupies that single line.
3. UTF-8 payload has a fixed byte limit.
4. Payload is an object with exact schema `pmm.control.v1`.
5. Unknown keys are rejected.
6. `concepts` is a non-empty array with a small fixed maximum.
7. Every token is a unique string satisfying a documented token grammar and
   length limit.
8. Every token either already has a definition or is accompanied through a
   separately authorized definition operation; undefined bindings must not
   silently become unretrievable associations.
9. Duplicate or conflicting envelopes reject the whole declaration.
10. Rejection creates a typed validation diagnostic linked to the assistant
    event and applies no declaration-derived CTL mutation.
11. Fallback behavior, if still applicable after rejection, remains explicitly
    runtime-attributed; it is never relabeled as model authorship.

Successful declarations should retain the current attribution invariant:

> `model_declared.origin_event_id` identifies the assistant event containing the
> accepted structured declaration.

Effective associations and attribution assertions remain separate. A later
valid model declaration may coexist with an earlier fallback assertion without
duplicating the effective CTL association.

## Evidence and authority boundaries

An association-only envelope may label the current turn without citing raw
evidence because the assistant directly authored that turn. It must not gain
authority to bind arbitrary earlier events.

If a future envelope refers to historical event IDs, each referenced event must
be validated against the appropriate formal evidence channel. Today,
`selection_ids` proves availability only through the current turn's raw-event
evidence channel. It does not prove availability through CTL, thread summaries,
graph state, identity, RSM, or open-commitment projections.

Concept authorship also does not establish semantic truth. A valid envelope can
prove that the model deliberately declared an association; it cannot prove that
the association is accurate, useful, or supported.

## Evaluation before implementation

Evaluate candidate parsers offline before allowing ledger mutation:

1. Freeze a corpus containing the Granite and Gemma transcripts, existing
   protocol-gate outputs, ordinary fenced JSON examples, malformed markers,
   duplicated controls, quoted controls, and truncated responses.
2. Label intended declarations before running candidate parsers.
3. Report declaration precision and recall, false mutation count, rejection
   reason distribution, and exact attribution output.
4. Require zero mutations from generic prose and generic fenced JSON in the
   adversarial corpus.
5. Test association idempotency and coexistence with prior fallback attribution.
6. Test undefined-token handling and later lexical retrieval.
7. Run the same protocol-conformance gate across multiple model families and
   provider adapters.
8. Re-run a natural conversation without explicitly requesting controls and
   measure natural capture separately from instructed compliance.

Only after the envelope, schemas, failure behavior, migration posture, and
cross-model acceptance criteria are frozen should a parser patch be considered.

## Explicit deferrals

This audit does not recommend:

- extracting concepts heuristically from prose;
- treating every fenced JSON block as a declaration;
- rewriting historical assistant events or binding assertions;
- changing the universal fallback based on these sessions;
- granting `REFLECT:` arbitrary CTL mutation authority;
- treating model declaration as evidence of correctness;
- implementing the parser before the offline corpus and acceptance criteria are
  approved.
