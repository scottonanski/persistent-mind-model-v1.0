# Nonproduction concept-authorship evaluation

This directory evaluates the proposed `PMM-CONTROL` protocol without importing
or changing PMM's production runtime parser. It has no ledger-writing path.

The offline harness validates a frozen adversarial corpus, reports parser
precision/recall and false acceptances, and simulates attribution/idempotency in
memory. Historical Granite and Gemma transcripts are loaded only when their
preserved SHA-256 values match the corpus manifest.

The conformance harness supplies one identical experimental protocol primer to
each configured model. Its outputs are artifacts, not production PMM turns.

```bash
.venv/bin/python experiments/concept_authorship_channel/offline_harness.py
.venv/bin/python experiments/concept_authorship_channel/conformance_harness.py
```

Generated reports, provider outputs, and checksums are written under
`artifacts/` and are intentionally ignored.
