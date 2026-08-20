# PMM Current Status and Roadmap

**Audited runtime baseline:** `e3fe3a625587732ae748b14bde4db66e17b67be5`

**Status date:** 2026-08-20

This is the active project-status document. It records where PMM stands and what
comes next. Completed implementation history belongs in Git, not in an
ever-growing roadmap.

## Direction

PMM is building a reconstructable cognitive history around a language model:

```text
experience
  -> interpretation
  -> interpretation of interpretation
  -> identity, ontology, or policy revision
  -> commitment
  -> outcome
  -> later reinterpretation
```

The current implementation provides substantial infrastructure beneath that
lifecycle. It does not yet make the complete sequence a governed first-class
mechanism.

## Where the project is now

### Strong current substrate

- Canonical events are stored in a hash-linked SQLite ledger.
- Managed writers use database-scoped ownership and fencing.
- `Mirror`, `MemeGraph`, and `ConceptGraph` are required rebuildable projections
  with fixed-watermark freshness barriers.
- Managed turns preserve complete assistant output or an explicit terminal
  generation failure.
- One prior completed managed pair is rendered as bounded non-evidentiary
  conversational context.
- Retrieval combines concepts, graph topology, commitment episodes, summaries,
  and optional vector stages while recording selection provenance.
- Commitment opens and closes use transactional lifecycle guards and exact
  provenance on new assistant-produced events.
- A stable CID can expose separate current and historical open-to-close episodes
  without flattening them into one current obligation.
- R06 v1 makes governed identity adoption subject/token-specific, requires an
  explicitly related reflection anchor and assistant claim provenance, records
  typed rejection, and filters legacy or invalid adoptions from authoritative
  projections.
- Vector-overlap maintenance records bounded, attributable diagnostics without
  presenting them as complete retrieval verification.

### Important current limits

- Reference requirements and permitted roles are not governed uniformly.
- Declared evidence can be referentially valid without being relationally or
  semantically adequate.
- Unknown structured claim types still have a fail-open compatibility path.
- Reflection and self-model terminology still covers mechanisms with different
  cognitive meaning.
- Concept supersession lacks a complete ledger-aware relationship policy.
- Forced concept retrieval can include material without a separate relevance
  decision once a privileged concept has been seeded.
- Diagnostics, telemetry, summaries, and maintenance are not uniformly isolated
  from cognitive projections.
- The complete commitment-to-outcome-to-later-reinterpretation lifecycle is not
  yet mandatory.
- Semantic adequacy remains unresolved; typed structure does not prove meaning.

## Completed since the prior baseline

- The reference-policy matrix audit inventoried the current reference-bearing
  and authority surfaces and selected R06 identity adoption for a bounded
  falsifiable guarantee.
- R06 v1 policy, implementation, verification, publication, and merge are
  complete. The implementation is on `main` at the audited baseline above.
- The bounded commitment outcome/later-review contract was selected from the
  existing matrix, explicitly authorized, and implemented. It governs one exact
  outcome per closed commitment episode and zero or more exact later reviews;
  preserves invalid attempts durably; isolates legacy outcome learning and
  identity/adaptive consumers; and exposes only validated relationships through
  MemeGraph and episode-aware retrieval.
- The bounded reflection reinterpretation contract extends one authoritative
  outcome review with zero or more explicit later reinterpretations. It requires
  exact review and episode lineage, managed-assistant provenance, durable typed
  rejection, idempotent replay, and one authoritative `reinterprets` edge per
  event. General R02 remains unchanged, and the new relationship is isolated
  from Mirror, RSM, identity, commitment state, adaptive learning, and policy.
- Reflection reinterpretation post-change verification passed `583` tests,
  Ruff across `pmm` and `pmm/tests`, exact-diff whitespace checks,
  rebuild/incremental and reopen parity, exact retrieval provenance, hostile
  malformed/forged/raw/wrong-lineage/recursive counterexamples, and a final
  hostile production-path review with no actionable high- or medium-severity
  defect.
- Post-change verification passed `575` tests, Ruff across `pmm`, exact-diff
  whitespace checks, rebuild/incremental parity, hostile malformed-input and
  producer-forgery counterexamples, and final hostile exact-diff review with no
  actionable high- or medium-severity defect.
- The implementation was published in PR #22 and merged on `main` at the
  audited runtime baseline above; implementation commit `c0ad07d` is retained
  in the merge history.

## Completed surface selections

The matrix has already supplied the comparison evidence. The remaining
candidates differ mainly in how directly they advance the cognitive lifecycle
and how much unsettled policy they require:

| Candidate | Matrix-grounded selection note |
|---|---|
| Identity conflict, replacement, and coherence | Important after adoption, but conflict authority and replacement semantics remain wholly unsettled. |
| Reflection-target and reinterpretation roles | R02 is optional and weakly checked, making this central but broad unless narrowed to one role. |
| Concept supersession and version history | R10 has concrete lineage, ordering, version, successor, and cycle gaps; primarily topology hardening. |
| Forced-concept relevance and attractor control | R13/R14/R23 can steer retrieval without complete target or authority checks; relevance policy remains unresolved. |
| Hybrid-retrieval reproducibility / vector verification | R17/R17D provide attributable diagnostics but do not reproduce or prove the full hybrid selection. |
| Diagnostic, telemetry, summary, and maintenance isolation | Several rows can influence projections or replay, but this spans multiple distinct producers and consumers. |
| Governed commitment outcome and later review | R07/R08 already identify exact episodes, while episode consumers lack mandatory outcome and later-review links. |
| Controlled generation retry | A runtime reliability policy, less directly relational than the current roadmap direction. |
| Concept-authorship experiment | Explicitly bounded nonproduction research whose stopping conditions remain closed. |
| Continuity-fallback ablation | Explicitly bounded to its isolated experiment harness rather than a production relational guarantee. |

**Selected and completed:** the governed commitment outcome and later-review
lifecycle, bounded to explicit links from an outcome and a later review to one
exact commitment episode. It extends the governed R07/R08 episode substrate into
the missing `commitment -> outcome -> later reinterpretation` portion of PMM's
stated cognitive lifecycle. The implemented contract is recorded in
`docs/commitment-outcome-later-review-policy.md`.

**Selected and completed:** governed reinterpretation of one exact authoritative
outcome review. The bounded contract permits multiple distinct later
reinterpretations with exact replay idempotency, rejects ordinary or recursive
targets, and exposes the relationship only through MemeGraph and exact-episode
retrieval. The implemented contract is recorded in
`docs/reflection-reinterpretation-policy.md`.

There is no authorized next implementation after this bounded surface. The
remaining candidates below require a new selection and explicit authorization.

## Later candidates

These remain unselected. Their order is not priority.

- Identity conflict, replacement, and coherence policy.
- Concept supersession and version-history integrity.
- Forced-concept relevance and attractor control.
- Complete hybrid-retrieval reproducibility or narrower vector-stage
  verification.
- Isolation of diagnostics, telemetry, summaries, and maintenance from cognitive
  projections.
- Controlled generation retry policy.
- Further concept-authorship research only after its nonproduction stopping
  conditions are deliberately reopened.
- Continuity-fallback ablation only through its isolated experiment harness.

## Development rule

For each selected task:

1. establish repository state and one falsifiable guarantee;
2. trace every production, validation, preservation, projection, retrieval, and
   promotion path before editing;
3. identify policy choices explicitly;
4. implement only the authorized scope;
5. retrace the lifecycle after the change;
6. run focused and broader verification proportionate to risk;
7. inspect the exact diff and publication scope.

Documentation, passing tests, and model agreement cannot substitute for
production-path evidence.
