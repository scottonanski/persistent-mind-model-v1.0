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

### B. Dedicated versioned control envelope with narrow ontology growth

Permit one exact final line after the conversational response:

```text
PMM-CONTROL:{"schema":"pmm.control.v1","concepts":["identity.adaptive_continuity"]}
```

The prefix expresses mutation intent; the schema discriminator identifies the
contract; the single-line suffix remains ordinary deterministic JSON parsing.
This aligns with the marker channel that both tested model families already use
after prose. Generic JSON and generic Markdown fences remain inert.

Association-only authority is not sufficient for PMM. The discoveries that
motivated this audit were new concepts, not merely references to established
tokens. The same envelope must therefore support a narrowly bounded definition
plus immediate grounding:

```text
PMM-CONTROL:{"schema":"pmm.control.v1","define":[{"token":"continuity.productive_friction","definition":"Visible struggle while integrating new understanding with prior knowledge, indicating honest revision rather than retrospective invention."}],"concepts":["continuity.productive_friction"]}
```

The accepted authority remains deliberately smaller than full `concept_ops`:

- bind accepted tokens to the current user and assistant events;
- bind them to commitments opened by the same assistant event;
- define a previously unknown token only when that token is immediately bound
  through the same envelope;
- create `model_declared` attribution assertions linked to that assistant event;
- do not alias, relate, redefine, supersede, or bind arbitrary historical
  events.

Every new definition token must appear in `concepts`. Every token in `concepts`
must either already exist or have exactly one definition in the same envelope.
Redefinition, collisions, duplicate definitions, dangling definitions, and
partial acceptance reject the entire envelope.

Column-zero placement alone is insufficient because a line at column zero may
still occur inside a Markdown fence or in a quoted example followed by more
prose. The envelope must be the final non-empty response line, start at column
zero, be outside all Markdown fences, and be the only `PMM-CONTROL:` occurrence
that could be interpreted as an envelope. Its JSON must be complete on that one
line with no trailing content.

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

The smallest promising design is **B**, including its narrow new-concept
definition authority, optionally followed later by the reflection-specific
extension in **C**.

Use one provider-neutral, versioned, exact-prefix control line after prose.
Retire the contradictory expectation that model-authored concepts must be both
first-line and subordinate to a conversational response. Do not accept generic
fenced JSON or scan later prose for objects.

Declaration validation should be all-or-nothing:

1. Exactly zero or one `PMM-CONTROL:` line per successful response.
2. The envelope is the final non-empty response line.
3. The prefix starts at column zero, is outside Markdown fences, and the
   complete payload occupies that single line with no trailing content.
4. No other `PMM-CONTROL:` envelope appears in the response, including inside a
   fence or quoted example; ambiguity rejects the declaration.
5. UTF-8 payload has a fixed byte limit.
6. Payload is an object with exact schema `pmm.control.v1`.
7. Only `schema`, `concepts`, and optional `define` keys are allowed.
8. `concepts` is a non-empty array with a small fixed maximum.
9. Every token is a unique string satisfying a documented token grammar and
   length limit.
10. `define`, when present, is a bounded array of objects containing only
    `token` and `definition`; definition text has a fixed length bound.
11. Every newly defined token also appears in `concepts`, preventing ungrounded
    definition deposits.
12. Every token in `concepts` either already exists or has exactly one
    definition in the same envelope.
13. An existing token cannot appear in `define`; redefinition, token collision,
    duplicate definition, or duplicate concept rejects the whole declaration.
14. Aliases, relations, supersession, historical bindings, and unknown keys are
    not part of this schema.
15. Duplicate or conflicting envelopes reject the whole declaration.
16. Rejection creates a typed validation diagnostic linked to the assistant
    event and applies no declaration-derived CTL mutation.
17. Fallback behavior, if still applicable after rejection, remains explicitly
    runtime-attributed; it is never relabeled as model authorship.

Successful declarations should retain the current attribution invariant:

> `model_declared.origin_event_id` identifies the assistant event containing the
> accepted structured declaration.

Effective associations and attribution assertions remain separate. A later
valid model declaration may coexist with an earlier fallback assertion without
duplicating the effective CTL association.

### Legacy-channel coexistence

The current first-line JSON channel should remain supported initially so this
change does not silently break existing compliant models or historical test
contracts.

- A response may use the legacy header, the final-line envelope, or neither.
- Identical concept sets from both channels are accepted as one declaration and
  produce one effective association plus the appropriate model attribution
  assertion.
- Conflicting concept sets, definitions in one channel that collide with the
  other, or independently meaningful dual declarations reject the structured
  declaration with a typed diagnostic rather than selecting a winner.
- Existing events and binding assertions remain immutable.
- A runtime fallback already recorded on an earlier turn is never
  retrospectively relabeled when the model later declares the same association.

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

Structural validation and conceptual evaluation must remain separate:

- Runtime validation covers placement, fence state, schema, bounds, token
  grammar, uniqueness, definition grounding, existing-token collisions, and
  all-or-nothing application.
- Runtime validation does not claim that a definition is insightful, relevant,
  accurate, or useful.
- Definition relevance and relational quality belong in blinded experimental
  evaluation.

## Evaluation before implementation

Evaluate candidate parsers offline before allowing ledger mutation. This phase
tests parser safety, not whether models will emit a protocol they had not yet
been taught:

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
8. Report structural precision and recall, false accepted mutation count,
   rejection-reason distribution, attribution output, idempotency, and
   effective-association behavior.

After offline safety evaluation, run a separate nonproduction emission and
conformance experiment. Supply the same experimental primer and exact protocol
to every tested model family and provider adapter. Do not create family-specific
parser rules or prompts. Different compliance rates are compatibility results,
not reasons to loosen the contract.

Measure separately:

- explicit compliance when a test prompt requests an envelope;
- **spontaneous appropriate-use rate** during ordinary conversation after the
  system primer teaches the channel but the user does not request control
  syntax;
- final-line, column-zero, and outside-fence placement compliance;
- schema, bounds, and token-grammar validity;
- new-definition grounding and collision behavior;
- overuse and false declarations;
- blinded definition relevance and relational quality.

Historical Granite and Gemma responses remain valuable adversarial parser
inputs, but they cannot measure spontaneous appropriate use of a syntax those
models were never shown.

Collect safety and conformance evidence first. Then freeze the protocol and
acceptance criteria. Only after that freeze should a production parser patch be
considered.

## Explicit deferrals

This audit does not recommend:

- extracting concepts heuristically from prose;
- treating every fenced JSON block as a declaration;
- rewriting historical assistant events or binding assertions;
- changing the universal fallback based on these sessions;
- granting `REFLECT:` arbitrary CTL mutation authority;
- treating model declaration as evidence of correctness;
- depositing new definitions without binding them to the discovery turn;
- accepting partial envelopes when any definition or concept fails validation;
- creating model-family-specific parsing or acceptance rules;
- implementing the production parser before the offline safety evaluation,
  cross-model conformance evidence, and separate approval.
