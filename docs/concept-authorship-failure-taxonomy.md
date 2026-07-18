# Concept-authorship control failure taxonomy

Status: post hoc classification of preserved nonproduction trials. No new model
calls were made, and no production or candidate-parser behavior was changed.

## Scope and method

This audit covers every emitted `PMM-CONTROL` envelope rejected by the frozen
candidate parser in primer-v1 and primer-v2 conformance trials. Structurally
accepted but semantically inappropriate declarations are excluded: they are
overuse failures, not malformed outputs.

Each rejected emission has:

- the parser's primary rejection reason, preserving validation order; and
- every independently observable taxonomy category, so an early schema failure
  does not hide a malformed definition or copied metasyntax.

The categories were fixed by the requested audit: wrong placement,
missing/incorrect schema, invalid token, missing `define`/`concepts` linkage,
placeholder/metasyntax leakage, invalid JSON, extra keys, and other. `Other`
includes exact failures such as redefinition and invalid `define` shape. A
malformed `define` representation is not counted as a linkage error because its
token linkage cannot be inspected reliably.

## Aggregate result

There were 21 malformed outputs: six in primer v1 and fifteen in primer v2.

Primary parser failures are mutually exclusive:

| Primary failure | Count |
|---|---:|
| Missing/incorrect schema (`INVALID_SCHEMA`) | 14 |
| Invalid JSON | 2 |
| Wrong placement: inside fence | 1 |
| Wrong placement: not final | 1 |
| Invalid definition structure | 1 |
| Redefinition of an existing concept | 1 |
| Definition not grounded in `concepts` | 1 |

Multi-label categories expose secondary defects and therefore do not sum to 21:

| Category | Outputs |
|---|---:|
| Other | 15 |
| Missing/incorrect schema | 14 |
| Placeholder/metasyntax leakage | 9 |
| Extra keys | 8 |
| Wrong placement | 2 |
| Invalid JSON | 2 |
| Invalid token | 1 |
| Missing `define`/`concepts` linkage | 1 |

## Trial-level pattern

### Primer v1

All six malformed emissions came from Granite and were heterogeneous: one
redefinition, one placeholder definition ungrounded in `concepts`, one trailing
control, one non-JSON abstention marker, one missing schema, and one fenced
control. Gemma's emitted controls were structurally accepted, including its
inappropriate declarations.

Primer v1 therefore demonstrated that a copyable valid example can teach exact
serialization, but can also be replayed as data and encourage declarations on
ordinary prompts.

### Primer v2: Granite

All ten Granite responses emitted controls, including the four prompts requiring
abstention. Eight used an `object` wrapper derived from the deliberately invalid
metasyntax and consequently had both missing/incorrect schema and extra keys.
The remaining two were invalid JSON and an invalid string-valued `define`.

This is not a single small omission. Granite systematically treated descriptive
metasyntax as output structure and still did not apply the abstention rule. A
nonce-guarded valid template may improve its serialization, but this corpus does
not support expecting the nonce alone to correct its semantic overuse.

### Primer v2: Gemma

Gemma emitted five controls and correctly abstained on all four negative prompts.
All five emitted controls omitted the required schema. One otherwise had the
intended existing-concept shape. Four also serialized `define` incorrectly—as
nested arrays or flat strings—and one token had leading whitespace. The mixed
explicit trial also omitted the requested existing `memory.persistence` binding.

Gemma's failures are more systematic and mechanically local than Granite's:
selectivity was correct, placement was perfect, and the dominant errors were a
missing constant schema field plus definition-object shape. This is affirmative
evidence that a nonce-guarded valid template is worth testing for at least one
model family under identical provider-neutral rules.

## Decision implication

A primer-v3 nonce experiment is justified, but not yet evidence for production:

- retain primer-v2's abstention criteria;
- show one fully shaped valid envelope;
- use reserved example tokens and definitions that the parser must reject;
- require a fresh per-turn nonce and reject missing, stale, or copied nonces;
- preregister zero accepted negative declarations and zero reserved-value
  persistence;
- keep the same parser rules and primer across models.

The nonce must guard freshness and example copying; it must not turn a semantically
inappropriate current-turn declaration into an acceptable mutation. If exact
serialization remains unreliable after that bounded test, the evidence favors a
separate schema-constrained encoding pass or provider structured output rather
than loosening the parser.

Machine-readable records, exact per-output details, and source hashes are in
`experiments/concept_authorship_channel/artifacts/failure-taxonomy-01.json`.

