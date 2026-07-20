# Contributing to Persistent Mind Model

The [PMM Cognitive Charter and Deviation Audit](docs/PMM-COGNITIVE-CHARTER.md)
is the governing architectural baseline. This document is the engineering
contract beneath it. Current code determines what production behavior exists;
neither current code nor this contract may silently redefine PMM's intended
cognitive architecture.

PMM combines model-authored cognition with a deterministic persistence,
governance, and projection substrate. Contributors must preserve that boundary.

## 1. Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[full,dev]"
pytest -q
ruff check path/to/changed.py
black --check path/to/changed.py
git diff --check
```

PMM supports Python 3.9 and later, as declared in `pyproject.toml`. Run tests and
formatting checks proportionate to the changed scope. A documentation-only
change requires documentation review and `git diff --check`; it does not require
unrelated pre-existing Python formatting findings to be repaired in the same
commit. Report every broader check attempted and every failure rather than
silently narrowing the command after it fails.

## 2. Architectural contract

### Preserve cognition; do not regenerate it on replay

Model-authored interpretations and reflections are valid nondeterministic inputs.
Once produced, their exact recorded form and applicable provenance become part of
canonical history. Replay reconstructs what happened; it does not call a model to
regenerate the same thought.

Determinism applies to:

- canonical serialization and ledger writes;
- validation and rejection decisions;
- authorized promotion and state transitions;
- deterministic projections and replay;
- idempotency and convergence rules;
- recorded provenance, selection, and relationship handling.

Do not claim that a model would reproduce byte-identical cognition from the same
prompt. Do require sufficient recorded information to reconstruct the cognition
that actually occurred and how PMM governed it.

### Keep lifecycle layers distinct

Every change must distinguish, where applicable:

```text
utterance history
  -> extracted candidate
  -> validation result
  -> canonical event or distinct failure event
  -> deterministic projection
  -> authoritative promotion or state mutation
  -> later retrieval or model-visible context
```

A preserved utterance is not automatically a canonical claim. A canonical event
is not automatically authoritative state. A projection is not proof of semantic
truth.

### Keep cognitive and operational records distinct

Interpretation, reflection, meta-reflection, identity, ontology, commitment,
outcome, and self-governance use the meanings defined by the Cognitive Charter.

Diagnostics, telemetry, deterministic summaries, counters, retrieval checks,
and maintenance output must not masquerade as those cognitive faculties. An
operational record may become the subject of a later model-authored
interpretation, but it is not itself that interpretation.

Do not select a new event vocabulary, schema, migration, or production rename as
an incidental part of another patch. Those choices require explicit design and
authorization.

## 3. Ledger and governance rules

### Canonical history

- Preserve accepted user and model outputs exactly within their defined
  canonical representation.
- Preserve rejected structured attempts in their correct historical or failure
  form without promoting them as accepted state.
- Never rewrite or delete historical events to make a new projection or policy
  appear retroactive.
- Every derived event must identify the inputs, source, version, or other
  provenance required by its stated guarantee.
- Never emit events merely to satisfy a test fixture.

### Writer governance

- Canonical writes must use the governed EventLog writer path.
- Do not bypass writer ownership, fencing, transactional predecessor selection,
  or required projection delivery.
- Source labels are historical metadata, not sufficient authorization by
  themselves.
- A failure after canonical commit must remain distinguishable from a failure
  before commit.

### Deterministic projections

- Authoritative projections must be rebuildable from canonical ledger history.
- Incremental delivery and full replay must converge within the projection's
  declared scope.
- `sync()`, `add_event()`, and equivalent incremental operations must be
  idempotent.
- Required projection failures must follow the established fail-closed delivery
  path; optional observers must not silently become authoritative.
- No process-local cache may become hidden authoritative state.

### Idempotency and convergence

- Define idempotency at the operation's actual identity boundary; do not equate
  similar text with the same historical act.
- A deterministic derived operation with no new declared state or observation
  should converge without duplicate effects.
- Later re-evaluation under a new algorithm, policy, or verifier version may be
  preserved separately when its version is part of the operation identity.
- Do not deduplicate distinct model-authored or user-authored historical outputs
  merely because their content matches.

### Validation and promotion

- Trace every producer, alternate producer, validator, rejection path,
  projection, retrieval consumer, and promotion path affected by a change.
- A validator working when invoked does not establish universal coverage.
- Distinguish a missing or bypassed check from an incomplete check.
- Existence of a target establishes referential validity only; it does not prove
  that the target may serve the declared role.
- A permitted relationship does not prove semantic warrant.
- Preserve undecided policy rather than embedding it in a parser, default, or
  compatibility path.

### Structured controls and heuristics

- Canonical control markers and authoritative state transitions must use explicit
  structured parsing and validation.
- Heuristics used for indexing, retrieval, diagnostics, or telemetry must be
  bounded, attributable, testable, and described as heuristics.
- Heuristic output must not be promoted as model-authored interpretation,
  identity, ontology, or semantic truth.
- Regex or keyword matching must not become an undocumented authority boundary.

### Configuration and autonomy

- Credentials and provider access may use environment variables. Durable PMM
  behavior and policy must remain explicit and auditable.
- Interactive, one-shot, MCP, replay, and test surfaces may have different
  documented autonomy lifecycles. Do not claim autonomy is universally active
  when a supported path disables it.
- Autonomous mutations must use the same canonical ledger, validation, writer,
  and projection-governance paths as other mutations.
- Scheduling and maintenance are operational autonomy; do not describe them as
  reflective self-governance unless the Cognitive Charter lifecycle is actually
  enforced.

## 4. Architecture audit requirements

Changes affecting PMM architecture, runtime behavior, validators, event
relationships, projections, identity, commitments, retrieval, or claimed
guarantees must follow the repository's PMM development-auditor workflow.

Before implementation:

1. Record the branch, revision, and working-tree state.
2. State one falsifiable guarantee.
3. Trace production, extraction, validation, rejection, preservation, canonical
   recording, projection, retrieval, and promotion.
4. Find alternate producers, direct appends, compatibility paths, optional
   fields, defaults, fail-open handling, and silent degradation.
5. Identify any policy choice not already settled by the charter or an explicit
   authorization.

After implementation:

1. Retrace the complete affected lifecycle.
2. Verify that alternate paths do not provide weaker coverage or enforcement.
3. Run focused tests and the appropriate broader suite.
4. Inspect the complete diff and report all verification not performed.
5. State the strongest conclusion supported by the weakest relevant path.

Documentation, tests, model consensus, and intended design do not substitute for
production-path analysis.

## 5. Testing requirements

- Add direct tests for new modules and behavior.
- Test both accepted and rejected paths, including omission, malformed input,
  duplicate execution, replay, and alternate producers where relevant.
- Verify historical preservation separately from canonical promotion.
- Verify incremental projection behavior against full replay.
- Treat passing tests as evidence for their exercised conditions, not as proof
  that uninspected bypasses do not exist.
- Use representative bounded fixtures for ordinary tests and reserve large-ledger
  runs for targeted performance or lifecycle verification.
- Do not stub or simulate an unimplemented guarantee and then document it as
  production behavior.

## 6. Documentation rules

- Describe current production behavior separately from intended architecture and
  proposed policy.
- Qualify guarantees by their actual producer, validator, projection, and
  promotion scope.
- Preserve historical completion records; add a new audit boundary rather than
  silently broadening an older claim.
- Link architectural claims to the Cognitive Charter and implementation claims
  to current production evidence.
- Update the roadmap or relevant status document when a user-visible or
  architectural boundary changes.
- Do not rewrite historical ledger artifacts to match current terminology.

## 7. Commit and publication discipline

- Keep one logical change per commit.
- Do not combine documentation governance, runtime changes, schema changes, or
  migrations unless explicitly authorized as one scope.
- Review staged, unstaged, and untracked files before committing.
- Use clear imperative commit messages.
- Run `git diff --check` and all checks appropriate to the changed scope.
- Do not push, open a pull request, or publish a release unless that external
  action is authorized.

## 8. Current implementation freeze

The Cognitive Charter currently freezes:

- R17 implementation;
- the reference-policy matrix;
- R06 and R07 enforcement;
- new cognitive semantics;
- event-vocabulary and schema selection;
- component renaming;
- historical migrations or reinterpretation;
- runtime remediation inferred from the charter.

Documentation may preserve the approved architecture, reconcile governance, and
organize undecided work. It must stop before selecting or implementing runtime
changes.

## Summary

PMM's engineering contract is deterministic preservation, reconstruction,
validation, promotion, projection, and replay around a model-authored cognitive
lifecycle. Determinism governs how cognition is recorded and used; it does not
require a generative model to think the same thought twice.
