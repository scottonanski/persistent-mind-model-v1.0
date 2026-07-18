# Concept-authorship channel: safety and conformance evidence

Status: nonproduction evidence report. No production parser, primer, fallback,
retrieval, or ledger behavior was changed.

Design amendment commit: `95f85e3`  
Frozen safety corpus commit: `c0d23fb`  
Frozen conformance trials commit: `1243096`
Frozen primer-v2 trials commit: `dc96beb`

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

## Primer-v2 conformance result

Primer v2 changed only the nonproduction teaching prompt. The candidate parser,
models, generation settings, existing-concept list, and ten trial prompts were
unchanged. The primer contained no syntactically valid control example. It used
deliberately invalid metasyntax, made abstention the default, and explicitly
excluded greetings, arithmetic, one-off advice, ordinary facts, examples, and
simple topic labels. The manifest and acceptance criteria were committed before
any model call. A subsequent harness-only commit fixed its direct-execution
import path before any trial ran; it did not alter the primer or criteria.

The preregistered gate failed:

| Measurement | Granite | Gemma |
|---|---:|---:|
| Explicit positive success | 0/3 | 0/3 |
| Explicit abstention success | 0/1 | 1/1 |
| Spontaneous appropriate use | 0/3 | 0/3 |
| Ordinary negative abstention | 0/3 | 3/3 |
| Controls emitted | 10 | 5 |
| Structurally accepted controls | 0 | 0 |
| Final-line placement when emitted | 10/10 | 5/5 |
| Column-zero placement when emitted | 10/10 | 5/5 |
| Accepted negative declarations | 0 | 0 |
| Placeholder copies | 0 | 0 |

Granite continued to invoke the channel on every negative prompt. Its controls
generally represented the invalid metasyntax as an `object` wrapper or supplied
`define` in the wrong shape. Gemma correctly abstained on all four negative
trials, and its emitted lines were close to the intended form, but they omitted
the required `schema` key. Some Gemma definitions also used nested arrays or
flat strings rather than definition objects. Its mixed explicit response omitted
the requested existing `memory.persistence` concept.

Thus removing a copyable example corrected neither model's structural
conformance, although it eliminated literal placeholder copying and separated
their selectivity behavior sharply. Granite remained both structurally
incompatible and nonselective under this primer. Gemma became appropriately
selective but structurally incompatible. No model met the frozen compatibility
criteria, and the global requirement that every emitted control be accepted
failed.

The masked quality worksheet is empty because the unchanged parser accepted no
definitions. Conceptual quality was therefore not scored; treating rejected raw
payloads as accepted definitions after observing the result would change the
measurement boundary post hoc.

This refines the previous lesson: parser safety remains strong on the frozen
offline corpus, but the teaching problem includes both *when* to declare and
how to express the exact schema without a copyable valid example. The result
still does not justify production implementation or model-family-specific
acceptance rules.

## Preserved artifacts

Generated artifacts are stored locally under:

- `experiments/concept_authorship_channel/artifacts/offline-safety-01/`
- `experiments/concept_authorship_channel/artifacts/conformance-01/`
- `experiments/concept_authorship_channel/artifacts/conformance-02-primer-v2/`

They contain the reports, exact model outputs, frozen manifest copy, masked
quality worksheet, quality scores, and checksum manifests.

Conformance report SHA-256:

```text
21c53c68c6c65fe199a5e7f0add8b7b443ed3c070c30c6329fed96c858c6285c
```

Primer-v2 manifest, report, and acceptance SHA-256 values:

```text
2548a1a8e1b460c628348bcaf974d118ac1bc3945308e7d23830dc4780236e14  manifest.json
4739b8a5e0e4789f0614933113f0ef965f033ce54bc86d09ae1044886bd3e976  report.json
76448bd9e03d1d397b22b2646ebdfb9a5f830eb166dae81321606fec9e461be8  acceptance.json
```

No production implementation is included in this result.
