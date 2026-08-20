# Contributing to Persistent Mind Model

The [PMM Cognitive Charter](docs/PMM-COGNITIVE-CHARTER.md) defines the intended
architecture. Current code establishes what is implemented. The
[System Guide](docs/PMM-SYSTEM-GUIDE.md) explains the current implementation,
and the [roadmap](pmm-improvement-progress.md) records the next selected task.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[full,dev]"
.venv/bin/pytest -q
```

PMM supports Python 3.9 and later.

## Architectural discipline

Keep these lifecycle layers distinct:

```text
utterance history
  -> extracted candidate
  -> validation result
  -> canonical event or distinct failure event
  -> deterministic projection
  -> authoritative promotion or state mutation
  -> later retrieval or model-visible context
```

A preserved utterance is not automatically a canonical claim. A canonical
event is not automatically authoritative state. A projection or graph edge is
not proof of semantic truth.

Determinism governs preservation, validation, promotion, projection, retrieval,
and replay of recorded cognition. It does not require a model to regenerate the
same words from the same prompt.

## Audit requirements

Changes affecting architecture, runtime behavior, validators, event
relationships, projections, identity, commitments, retrieval, or claimed
guarantees must use the repository's PMM development-auditor workflow.

Before implementation:

1. Record branch, revision, and working-tree state.
2. State one falsifiable guarantee.
3. Trace production, extraction, validation, rejection, preservation, canonical
   recording, projection, retrieval, and promotion.
4. Find alternate producers, direct appends, compatibility paths, optional
   fields, defaults, exception handling, and silent degradation.
5. Identify every policy choice not already settled and authorized.

After implementation:

1. Retrace the affected lifecycle.
2. Confirm alternate paths do not provide weaker coverage or enforcement.
3. Run focused tests and the appropriate broader suite.
4. Inspect the complete diff and report verification not performed.
5. State the strongest conclusion supported by the weakest relevant path.

A validator working when invoked is not a system guarantee. Tests corroborate
their exercised paths; they do not establish universal coverage.

## Ledger and projection rules

- Use governed EventLog writer paths for canonical writes.
- Do not bypass writer ownership, fencing, transactional predecessor selection,
  or required projection delivery.
- Preserve user and model output in its correct historical form.
- Preserve rejected structured attempts without promoting them as accepted
  state.
- Keep authoritative projections rebuildable from canonical events.
- Require replay and incremental delivery to converge within the projection's
  scope.
- Do not make a process-local cache hidden authoritative state.
- Do not rewrite historical events to make a new policy appear retroactive.

## Relationship and policy rules

- Trace every producer, validator, rejection path, consumer, and promotion path.
- Separate omitted checks from incomplete checks.
- Separate target existence from permitted-role validation.
- Do not infer authority from a source label alone.
- Do not silently choose reference requirements, roles, cardinalities, graph
  authority, semantic adjudication, schemas, or migration policy.
- Keep heuristics bounded, attributable, and outside authoritative semantic
  promotion unless explicitly governed.

## Testing

Run checks proportionate to the change:

```bash
.venv/bin/pytest -q path/to/focused/tests
.venv/bin/pytest -q
.venv/bin/ruff check path/to/changed.py
.venv/bin/black --check path/to/changed.py
git diff --check
```

Test accepted, rejected, omitted, malformed, duplicate, replay, and alternate
producer paths where relevant. Verify historical preservation separately from
canonical promotion.

Documentation-only changes require source review, link and command validation,
and `git diff --check`. They do not require unrelated runtime changes.

## Documentation

- Keep the README short and navigational.
- Keep the charter about intended architecture, not completion history.
- Keep the System Guide tied to current production code.
- Keep the roadmap limited to current state, boundaries, and next work.
- Replace stale active sections instead of appending chronology.
- Let Git history preserve superseded audits and completion records.
- Keep experiments under `experiments/` and clearly nonproduction.
- Update links whenever an active document is replaced or removed.

## Commits and publication

- Keep one logical change per commit.
- Do not combine documentation cleanup with runtime, schema, or migration work.
- Review staged, unstaged, and untracked files before committing.
- Run `git diff --check` and scope-appropriate validation.
- Do not push, open a pull request, merge, or publish without authorization.
