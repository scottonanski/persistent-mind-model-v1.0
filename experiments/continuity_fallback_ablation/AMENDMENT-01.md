# Amendment 01: protocol compatibility and experiment separation

This amendment was made after pilot 01 and before any replication run. Pilot 01
is retained unchanged under `artifacts/pilot-01`.

Pilot 01 showed two distinct issues: the selected model configuration did not
reliably emit PMM's exact machine-readable protocol, and the scenario produced
empty raw retrieval selections. It therefore could not isolate the universal
fallback's retrieval effects.

The original hypotheses and metric definitions at design commit `54484e7` are
unchanged. The execution is split into:

1. A **model-parameterized PMM protocol-conformance gate**. PMM owns the
   protocol. A result describes only whether a recorded model/provider/config
   emitted output that the existing PMM protocol accepted.
2. A **mechanistic fallback pilot** using identical scripted output and
   byte-identical initialized ledgers. This isolates deterministic CTL and
   retrieval consequences.
3. A later **naturalistic model study**. Model formatting compliance and
   stochastic generation are outcomes in that study, not hidden properties of
   the mechanistic ablation.

No production parser, primer, runtime option, or fallback behavior is changed by
this amendment. Naturalistic sessions remain exploratory until the selected
model configuration passes the protocol gate with an acceptable observed rate.
