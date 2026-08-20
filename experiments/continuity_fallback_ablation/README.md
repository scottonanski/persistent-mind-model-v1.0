# Continuity-fallback ablation

## Status

This is a nonproduction experiment. It compares PMM's universal
`identity.continuity` fallback binding with an experiment-local arm that omits
only assertions attributed to `runtime_continuity_fallback`.

The production runtime is not configurable through this harness. The
no-fallback arm uses an experiment-local `EventLog` subclass; all other runtime
behavior remains the repository implementation recorded in the manifest.

## Current conclusion

Pilot 01 did not pass its diagnostic gate. The selected model configuration did
not reliably emit PMM's existing machine-readable protocol, and the scenario
produced empty raw retrieval selections. That run could not isolate the
fallback's retrieval effect.

The experiment was therefore split into:

1. a model-parameterized protocol-conformance gate;
2. a deterministic mechanistic pilot using identical scripted output and
   byte-identical initialized ledgers;
3. a later naturalistic model study only after protocol compatibility is
   established.

A passing protocol gate describes one recorded model/provider/configuration. It
does not authorize a model-specific PMM protocol or a production fallback
change. No production policy has been selected from this experiment.

## Run

Deterministic mechanism preflight:

```bash
.venv/bin/python experiments/continuity_fallback_ablation/harness.py preflight
```

Original matched pilot:

```bash
.venv/bin/python experiments/continuity_fallback_ablation/harness.py pilot
```

Protocol gate and isolated mechanistic pilot:

```bash
.venv/bin/python experiments/continuity_fallback_ablation/harness.py protocol-gate
.venv/bin/python experiments/continuity_fallback_ablation/harness.py mechanistic-pilot
```

`protocol-gate` defaults to the model in `manifest-v2.json`; `--model` can select
another Ollama model without changing PMM's protocol.

Generated databases, transcripts, prompt captures, and reports go under ignored
`artifacts/`. Preserve that directory separately before replication because it
may contain private provider-facing context.

Historical preregistration, metric definitions, and the post-pilot amendment
remain available in Git history.
