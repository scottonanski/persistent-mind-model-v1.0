# Concept-authorship channel experiment

## Status

`PMM-CONTROL` remains nonproduction. This directory contains isolated harnesses
for evaluating whether a model can author durable concepts through a versioned,
strictly parsed control envelope. Nothing here is imported by PMM's production
parser or writes to a production ledger.

## Current conclusion

The candidate parser produced zero false accepted mutations on its frozen finite
safety corpora. Model behavior was the limiting factor:

- Granite did not demonstrate safe mutation judgment under the tested primers;
  its preregistered stopping rule fired.
- Gemma produced useful definitions and passed the reserved-template
  configuration, but adding a model-carried current-turn reference reduced
  spontaneous appropriate authorship from `14/15` to `7/15`, below the frozen
  compatibility gate.
- Deterministic turn-reference equality prevented stale replay in the frozen
  corpus, but the tested teaching design imposed material behavioral cost.

The channel is therefore not approved for production. The open question is:

> Can PMM guarantee freshness without making the conversational model serialize
> the freshness mechanism?

Any future work should compare runtime-bound structured tools, a separate
schema-constrained encoding pass, transactional current-turn activation, or
quarantined provisional authorship. Evaluation criteria must be frozen before a
new experiment. Do not resume Granite primer iteration without explicitly
reopening its stopping rule.

## Harnesses

```bash
.venv/bin/python experiments/concept_authorship_channel/offline_harness.py
.venv/bin/python experiments/concept_authorship_channel/conformance_harness.py
.venv/bin/python experiments/concept_authorship_channel/conformance_harness_v2.py
.venv/bin/python experiments/concept_authorship_channel/failure_taxonomy.py
.venv/bin/python experiments/concept_authorship_channel/conformance_harness_v25.py
.venv/bin/python experiments/concept_authorship_channel/score_quality_v25.py
.venv/bin/python experiments/concept_authorship_channel/turn_ref_experiment.py
.venv/bin/python experiments/concept_authorship_channel/score_quality_v3.py
```

The checked-in manifests and corpora freeze inputs for the corresponding
harnesses. Generated provider output, reports, databases, and prompt captures go
under ignored `artifacts/`; they may contain sensitive provider-facing context.

Historical design reports and trial narratives remain available in Git history.
