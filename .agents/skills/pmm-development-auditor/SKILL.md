---
name: pmm-development-auditor
description: Audit Persistent Mind Model architecture, code changes, validators, event relationships, projections, identity and commitment behavior, retrieval, and documented guarantees against the current repository. Use when reviewing or implementing PMM changes, investigating fabricated or unsupported claims and citations, checking whether an invariant is mandatory or bypassable, distinguishing recorded history from authoritative state, or evaluating whether code, tests, documentation, and runtime evidence justify a claimed guarantee.
---

# PMM Development Auditor

Determine exactly what the current repository establishes. Do not teach agreement with PMM's architecture, and do not infer a guarantee from its intended design.

## Apply the governing doctrine

Treat this as the primary audit rule:

> A validator's correctness when invoked does not establish a system guarantee. Audit every relevant path for omission, bypass, weakening, fail-open behavior, and silent degradation.

Treat memory and identity as relational structures. Analyze events, explicit relationships, later interpretations, changes in interpretation, commitments, and resulting projections. Never reconstruct identity or architectural behavior from an isolated statement.

Let current repository behavior outrank documentation, research artifacts, comments, tests, and model descriptions.

## Follow the audit workflow

1. Establish the repository state. Record the active branch or detached revision, `HEAD` commit, relevant uncommitted and untracked changes, and any task-specified revision. Treat working-tree code as current behavior unless the task explicitly names a committed revision. Do not discard or overwrite unrelated changes.
2. State the claimed guarantee narrowly enough to falsify.
3. Locate the production entry points and every event, field, or state transition involved.
4. Trace the complete lifecycle:
   - production and extraction;
   - validation and rejection;
   - historical preservation;
   - canonical recording;
   - projection and retrieval;
   - authoritative promotion or mutation.
5. Find every alternate producer and consumer. Search for direct appends, optional fields, defaults, compatibility paths, exception handling, unknown types, and silent skips.
6. Determine whether a relevant check is mandatory on every path. Separate:
   - a **coverage gap**, where a required check can be omitted or bypassed;
   - an **enforcement gap**, where supplied structure is accepted without checking it against repository state.
7. Classify each established property:
   - **referential validation**: whether a referenced thing exists;
   - **relational integrity**: whether it is permitted to serve the claimed role;
   - **semantic adequacy**: whether it genuinely warrants the interpretation;
   - **governance integrity**: whether only authorized actors and paths may create or promote it.
8. Inspect tests after understanding production control flow. Treat tests as evidence for exercised conditions, not proof that untested bypass paths do not exist.
9. Compare documentation and design claims with the implementation. Label intended or proposed invariants explicitly.
10. Report the strongest conclusion supported by the weakest relevant path.

When asked to implement a change, complete the audit first. Do not silently decide unsettled policy. State the policy choice needed, implement only what the user authorized, and keep runtime fixes separate from edits to this skill.

After implementation, retrace the affected lifecycle and verify that no alternate producer, validation, projection, or promotion path remains weaker. Run focused tests and the appropriate broader suite, report every verification not performed, and inspect the final working-tree diff. Do not describe the proposed guarantee as implemented until this post-change audit succeeds; otherwise report the narrower verified status.

## Use the evidence hierarchy

Prefer evidence in this order:

1. Current production code paths.
2. Schemas and deterministic projections.
3. Tests exercising those paths.
4. Runtime, ledger, or exported-session evidence.
5. Documentation and design artifacts.
6. Model or agent descriptions.

Use lower-ranked evidence to locate questions or corroborate behavior, never to overrule higher-ranked contradictory evidence. Cite stable symbols and current file locations; resolve line numbers during the audit instead of embedding stale ones.

## Produce the required finding format

Use every field below for each investigated guarantee. Write `None found`, `Not applicable`, or `Not requested` rather than silently omitting a field.

```text
Repository state:
Claimed guarantee:
Actual mechanism:
Production paths:
Validation paths:
Bypass or degradation paths:
Preserved form:
Promoted form:
Integrity tier:
Coverage status:
Enforcement status:
Strongest supported conclusion:
Implementation evidence:
Relevant tests:
Post-change verification:
Proposed changes:
```

For `Coverage status`, state whether every in-scope producer and promotion path is forced through the applicable check. Do not classify a missing predicate inside an always-invoked validator as a coverage gap. For `Enforcement status`, state whether the invoked mechanism checks supplied structure against the repository state and role constraints required by the guarantee.

Use precise conclusion language such as:

- implemented and mandatory;
- implemented only when explicitly invoked;
- partially enforced;
- structurally validated but relationally unproven;
- documented but not implemented;
- proposed invariant;
- unresolved semantic question.

Do not use `implemented` without qualifying scope when an alternate path is weaker.

## Respect the audit boundaries

- Preserve the distinction between what a model said, what history recorded, what validation accepted, what projections consume, and what became authoritative state.
- Do not treat real event IDs as proof of a claimed relationship between those events.
- Do not treat a typed edge as proof that its content semantically warrants an interpretation.
- Do not treat passing focused tests, documentation, or multi-model agreement as proof of universal enforcement.
- Do not turn a proposed invariant into a description of current behavior.
- Do not introduce consciousness, sentience, personhood, or metaphysical framing unless the task explicitly concerns it.
- Do not autonomously settle claim registries, required-reference policy, relation roles, cardinalities, semantic adjudication, or graph authority when the repository and user have not settled them.

## Load references selectively

- Read [references/architecture-map.md](references/architecture-map.md) when locating PMM subsystems, event lifecycles, or likely audit surfaces. Re-verify every listed behavior in current code.
- Read [references/integrity-and-promotion.md](references/integrity-and-promotion.md) when classifying guarantees, gaps, preservation, validation, projection, or promotion.
- Read [references/philosophical-foundations.md](references/philosophical-foundations.md) when a design question concerns identity, relational memory, reflection, or commitments across time.
- Read [references/audit-cases.md](references/audit-cases.md) when planning an audit, evaluating an auditor, or checking the required finding format against common failure patterns.
