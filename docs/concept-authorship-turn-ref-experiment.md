# Managed turn-reference experiment (v3)

Status: completed Gemma-only nonproduction freshness experiment. No production
parser, primer, fallback, retrieval, adapter, or ledger behavior changed.

Frozen design/corpus commit: `f0067e6`

## Design

V3 added one field to the reserved-template v2.5 protocol:

```json
"turn_ref": 300001
```

The expected value was a unique deterministic stand-in for PMM's current managed
user-event ID and was supplied separately in the system control context for each
generation. The model, ten prompts, five repetitions, output budget, temperature,
reserved template, abstention rules, and quality rubric matched v2.5. Granite was
not run because its preregistered v2.5 stopping rule had fired.

The compatibility gate allowed spontaneous appropriate use to fall by at most
one from the v2.5 result (`14/15` to `13/15`). Quality thresholds were 1.75/2
for relevance and 1.70/2 for relational quality.

## Offline final-envelope replay result

The 14-case frozen corpus tested correct, missing, wrong, stale, future, Boolean,
and reused turn references; verbatim and partial reserved-value copying; fenced
and non-final controls; and duplicate envelopes with different references.

| Measurement | Result |
|---|---:|
| Cases | 14 |
| Intended acceptances | 3 |
| False accepted mutations | 0 |
| Rejection-reason mismatches | 0 |
| Reused-later-turn mutations | 0 |
| Safety corpus | Passed |

This closes the evidentiary gap in the earlier audit: stale replay was tested on
the actual candidate final-envelope path, not inferred only from the legacy
first-line channel.

## Gemma conformance result

| Measurement | v2.5 | v3 |
|---|---:|---:|
| Explicit positive success | 15/15 | 15/15 |
| Explicit abstention | 5/5 | 5/5 |
| Spontaneous appropriate use | 14/15 | 7/15 |
| Ordinary negative abstention | 15/15 | 15/15 |
| Accepted negative controls | 0 | 0 |
| Structurally accepted positive emissions | 29/29 | 22/22 |
| Positive turn-reference failures | n/a | 0 |
| Accepted reserved values | 0 | 0 |

Every emitted positive control used the exact current reference and passed the
unchanged concept validation. Gemma continued to comply perfectly when directly
asked to declare, and it abstained on all 20 negative trials.

However, spontaneous appropriate use fell from `14/15` to `7/15`, below the
preregistered minimum of `13/15`. Gemma omitted all five replacement controls,
emitted only two of five rupture controls, and emitted all five storage controls.
These were safe omissions, not malformed or stale mutations, but the regression
is large and systematic enough that v3 fails its compatibility-cost gate.

The seven accepted spontaneous definitions scored 2.0/2 for both relevance and
relational quality. Thus `turn_ref` did not degrade the concepts that were
actually authored; it substantially reduced when Gemma chose to author them.

## Interpretation

Deterministic current-turn equality provides the intended freshness guarantee on
the frozen corpus. It also imposed meaningful behavioral cost under the tested
teaching design. The result does not support adding `turn_ref` to production as
currently prompted.

This does not show that freshness is unnecessary. It shows that combining
freshness instructions with the free-form semantic decision can suppress
appropriate spontaneous authorship even when mechanical compliance remains
perfect. Before another prompt iteration, compare whether freshness should be
handled by a separate schema-constrained encoding step or by runtime-managed
challenge/response that does not burden the semantic judgment.

Attestation remains bounded evidence, not a permanent guarantee of judgment on
unseen prompts. V3 neither resolves capability governance nor authorizes direct
production activation.

SHA-256:

```text
27e017efa3ff4750259bb3b6bd667b7c02f521846c0e3a0420bd02a0e816dd05  turn_ref corpus.json
1607cafcf8f7fde7babe4f960c4bef2eee7c67a765ebc66621ce959014cd8fa0  turn_ref report.json
f8b7129a0d86b1ce65b6b5af18bc1768147874cef40ecfb51f4bde419695a0d9  v3 manifest.json
a2ed1d4d39a06f1a608a6d8d6202c87b893e4f3a7d58577f3b0e2c54be97ccc8  v3 report.json
521b7e0164bf5b924114b3fed79398c3cf6d70fdc804350976d61410a3252e89  quality-scores.json
```

