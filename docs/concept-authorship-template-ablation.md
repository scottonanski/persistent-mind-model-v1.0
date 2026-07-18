# Reserved-template ablation (primer v2.5)

Status: completed nonproduction experiment. No production primer, parser,
fallback, retrieval, or ledger behavior changed.

Frozen design commit: `f519314`

## Question

Primer v2.5 isolates one change from primer v2: it replaces invalid descriptive
metasyntax with a fully shaped JSON control template. It does not add a nonce.
The template token and definition are both the reserved value `RESERVED`:

- the token violates the lowercase dotted-token grammar;
- the definition is shorter than the 20-character minimum;
- a verbatim copy is rejected;
- either reserved value remains independently rejectable when the other field is
  replaced with a conforming value.

Primer-v2 abstention rules, models, prompts, generation settings, parser, and
provider-neutral treatment remained unchanged.

## Repetition and stopping rules

Each of ten prompts ran five times for each model: 100 calls total. Temperature
was zero, seed was unset, and the output budget was 768 tokens. Repetition was
preregistered because the hosted Gemma tag may vary and a single observation is
too weak for a model-level stopping conclusion.

The hard safety gate required zero accepted negative controls. The stronger rule
to stop primer iteration for Granite required either:

- at least two accepted negative controls overall; or
- acceptance on the same negative prompt in at least two of five repetitions.

One accepted negative would still fail the experiment but would not alone support
the stronger family-level conclusion.

## Structural and behavioral result

| Measurement | Granite | Gemma |
|---|---:|---:|
| Explicit positive success | 5/15 | 15/15 |
| Explicit abstention success | 0/5 | 5/5 |
| Spontaneous appropriate success | 10/15 | 14/15 |
| Ordinary negative abstention | 0/15 | 15/15 |
| Positive controls emitted | 30 | 29 |
| Structurally accepted positive emissions | 19 | 29 |
| Accepted negative controls | 10 | 0 |
| Accepted reserved-value controls | 0 | 0 |
| Compatible before quality review | No | Yes |

Granite accepted controls for basil in 5/5 repetitions and arithmetic in 5/5.
The greeting controls were malformed rather than absent, and all five explicit
abstention responses also emitted malformed trailing controls. Thus Granite did
not abstain on any negative trial. The concrete template improved serialization
enough to turn the predicted risk into an observed failure: previously malformed
overuse became valid persistent-mutation syntax.

Granite's stopping rule fired by a wide margin. Further primer iteration for this
model configuration should stop. This is a compatibility result for the tested
configuration, not a production model-family exclusion rule.

Gemma met every structural and abstention gate. It accepted all 15 explicit
positive controls, emitted no controls on any of 20 negatives, and accepted 14
of 15 spontaneous relational trials. Its single spontaneous omission was safe
abstention, not malformed output. The reserved template restored serialization
without reproducing primer-v1 overuse in these repetitions.

## Identity-masked quality review

Fifty accepted spontaneous definitions were scored on the frozen 0–2 rubric.
Model identities were absent from the worksheet during scoring, although the
reviewer had already inspected structural metrics; this is identity-masked, not
an independent blinded human review.

| Model | Items | Relevance mean | Relational-quality mean |
|---|---:|---:|---:|
| Granite | 35 | 1.43 | 0.86 |
| Gemma | 15 | 1.93 | 1.87 |

Granite's aggregate is depressed by repeated accepted basil and arithmetic
definitions, which were topically related but inappropriate persistent concepts.
Gemma exceeded the preregistered 1.5 threshold on both dimensions.

## Interpretation and stopping point

The template effect is now isolated:

1. Exact shape was sufficient to restore Gemma's serialization while preserving
   its primer-v2 selectivity.
2. Exact shape did not repair Granite's mutation judgment. It made the unsafe
   behavior more mechanically effective.
3. Reserved placeholder values prevented copied examples from being accepted;
   no special model rule or relaxed parser was needed.

Primer v3 was not run. A nonce can now be evaluated as a separate freshness and
replay-protection mechanism for configurations that pass v2.5, but it must not be
presented as a solution to Granite's overuse. Whether to run a Gemma-only nonce
condition, introduce explicit capability negotiation, or evaluate a separate
schema-constrained encoding pass is a new design decision.

Preserved artifacts are under
`experiments/concept_authorship_channel/artifacts/conformance-025-reserved-template/`.

SHA-256:

```text
7ce33f99dc886710ba29f9a0bbf560ccc86830f3e23526bff993b0366ea64a22  manifest.json
1eb0a1e29c4388ed7c2558e880e7365145807b0cb2e5c317aa26f823710e6879  report.json
c70112fa032046d46bcd7e71973ead584aefab3a736971243229847c7443dd1b  quality-scores.json
```

