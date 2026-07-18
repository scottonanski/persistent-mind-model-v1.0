# Concept-authorship channel: safety and conformance evidence

Status: nonproduction evidence report. No production parser, primer, fallback,
retrieval, or ledger behavior was changed.

Design amendment commit: `95f85e3`  
Frozen safety corpus commit: `c0d23fb`  
Frozen conformance trials commit: `1243096`

## Scope

This evaluation separates two questions:

1. Can a candidate final-line `PMM-CONTROL` parser reject nonconforming and
   ambiguous inputs without false persistent mutations?
2. After receiving one identical provider-neutral experimental primer, do
   different model configurations use the proposed channel correctly and
   appropriately?

The parser existed only in the experiment harness. It simulated definitions,
effective current-turn associations, and `model_declared` attribution in memory;
it had no PMM ledger-writing path. The conformance harness called the models
directly through the existing Ollama adapter rather than changing PMM's
production primer or runtime.

## Offline safety result

The frozen corpus contained 43 cases:

- seven intended acceptances;
- ordinary Granite and Gemma natural outputs;
- valid existing-concept, new-definition, and mixed envelopes;
- generic and fenced JSON;
- controls inside and outside closed fences;
- quoted, middle, duplicate, malformed, truncated, and oversized controls;
- invalid schema, unknown keys, token errors, duplicate concepts and
  definitions;
- undefined tokens, dangling definitions, redefinition, and collisions;
- legacy-header-only, identical dual-channel, and conflicting dual-channel
  cases.

Result:

| Measurement | Result |
|---|---:|
| Cases | 43 |
| True acceptances | 7 |
| True rejections/non-declarations | 36 |
| False accepted mutations | 0 |
| False rejections | 0 |
| Precision | 1.0 |
| Recall | 1.0 |
| Expected rejection-reason mismatches | 0 |
| Simulated attribution/effective-state idempotency | Passed |

Accepted simulated assertions used `binding_origin=model_declared` and the
assistant event as `origin_event_id`. New definitions were accepted only when
the token also appeared in `concepts`; undefined, redefined, duplicated, or
ungrounded tokens rejected the complete declaration.

This proves the candidate's behavior only on the frozen finite corpus. It is not
a proof that all adversarial text is safe.

Offline report SHA-256:

```text
259cb4a299e6b9602da17c39cb8cca3639d4ee8694ce0a29d2f79e1d50c8c008
```

## Cross-model conformance result

Both configurations received the same experimental primer, schema, existing
concept list, output budget, and ten prompts. No family-specific rule or prompt
was used.

Models:

- `granite4.1:8b-q5_K_M` — digest `a15a247eea85`
- `gemma4:cloud` — recorded Ollama digest `b06ba4be71c0`

Generation used temperature zero, an unset seed, and a 768-token output budget.
The cloud tag may resolve to changing hosted service internals despite the
recorded local manifest digest.

### Structural and use results

| Measurement | Granite | Gemma |
|---|---:|---:|
| Explicit compliance/abstention | 0/4 | 4/4 |
| Spontaneous appropriate use | 0/3 | 3/3 |
| Appropriate abstention on ordinary prompts | 1/3 | 1/3 |
| Controls emitted | 8 | 8 |
| Structurally accepted controls | 2 | 8 |
| Final-line compliance when emitted | 6/8 | 8/8 |
| Column-zero compliance when emitted | 8/8 | 8/8 |
| Accepted overuse declarations | 2 | 2 |

Granite demonstrated that prefix emission and column-zero placement do not imply
schema conformance. Its failures included:

- redefining the existing `identity.continuity` token;
- defining the requested token while leaving the primer placeholder
  `namespace.token` in `concepts`;
- placing a valid-looking control before trailing content;
- emitting a textual `PMM-CONTROL: (no control emitted...)` line;
- emitting an empty object;
- placing a spontaneous declaration inside a fence.

Granite's two structurally accepted declarations occurred on arithmetic and
greeting prompts. Both copied the primer's literal `namespace.token` example and
were inappropriate overuse rather than successful concept discovery.

Gemma followed the structure in all eight emitted controls and correctly
abstained on arithmetic. It also overused the channel for basil advice and a
greeting, creating `botany.growth_habit` and `temporal.progression`. The channel
was therefore usable for Gemma but insufficiently selective under this primer.

The literal example in the experimental primer is a demonstrated copy hazard,
while the strong instruction to persist durable concepts is a demonstrated
overuse risk. These are protocol-teaching results, not reasons for
model-family-specific parsing.

## Conceptual quality review

Seven accepted spontaneous definitions were scored using the frozen 0–2 rubric.
The scoring worksheet omitted model identities, but the reviewer had already
seen the structural report; this was identity-masked rather than a fully
independent blinded human review.

Gemma's three definitions on prompts preregistered as appropriate received 2/2
for both definition relevance and relational quality:

- `truth.rupture`
- `cognitive.reconciliation`
- `structural.persistence`

They precisely named the prompted relational distinctions and had plausible
future retrieval value. Gemma's two overuse definitions were weaker or
irrelevant. Across all five accepted Gemma definitions, including overuse, both
means were 1.4/2.

Granite's two accepted definitions were copied placeholders on inappropriate
prompts and scored 0/2 for both dimensions.

Quality-score SHA-256:

```text
497a2c857e731034ddc6f63b53118efba1dfb257c4d20fcf2aee631517251307
```

## Interpretation

The experiment supports four bounded conclusions:

1. A final-line, outside-fence, versioned envelope with narrow definition-plus-
   grounding authority can be parsed deterministically with zero false
   acceptances on this corpus.
2. The same protocol can capture genuinely new, relationally useful concepts;
   it is not limited to associations with predefined tokens.
3. Protocol usability and selectivity differed sharply between the two model
   configurations under an identical primer. Those differences are model
   compatibility measurements, not justification for changing parsing rules by
   family.
4. The tested primer is not ready for production: Granite copied its placeholder
   and failed explicit conformance, while both configurations overused the
   channel on ordinary prompts.

The evidence does not justify a production parser implementation yet. A future
design decision should consider teaching the grammar without a copyable valid
placeholder and reducing overuse without weakening the parser. The protocol and
production acceptance criteria should be frozen only after that evidence is
reviewed and a separate implementation is approved.

## Preserved artifacts

Generated artifacts are stored locally under:

- `experiments/concept_authorship_channel/artifacts/offline-safety-01/`
- `experiments/concept_authorship_channel/artifacts/conformance-01/`

They contain the reports, exact model outputs, frozen manifest copy, masked
quality worksheet, quality scores, and checksum manifests.

Conformance report SHA-256:

```text
21c53c68c6c65fe199a5e7f0add8b7b443ed3c070c30c6329fed96c858c6285c
```

No production implementation is included in this result.
