# Continuity fallback ablation harness

The production runtime is not configurable here. The no-fallback arm uses an
experiment-local `EventLog` subclass that declines only binding assertions whose
attributed origin is `runtime_continuity_fallback`. All other runtime behavior is
the repository implementation at the recorded commit.

The manifest freezes the pilot prompts, relevance labels, provider settings,
model digest, and design commit before the pilot is run.

Run the deterministic mechanism preflight:

```bash
.venv/bin/python experiments/continuity_fallback_ablation/harness.py preflight
```

Run one real-model matched pilot pair:

```bash
.venv/bin/python experiments/continuity_fallback_ablation/harness.py pilot
```

Generated databases, full transcripts, prompt captures, and reports are written
under `artifacts/`, which is intentionally ignored because it may contain private
provider-facing context. Preserve that directory outside the repository before
running replications.
