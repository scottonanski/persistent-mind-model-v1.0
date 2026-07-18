# PMM Agent Guidance

## Required skill routing

Before acting, inspect the repository skills available under `.agents/skills`.

| Task scope | Required skill |
|---|---|
| Analyze, review, diagnose, document, or change PMM architecture, runtime behavior, validators, claims, event relationships, projections, identity, commitments, retrieval, or claimed guarantees | `$pmm-development-auditor` |

For every task in that scope:

1. Use `$pmm-development-auditor` before substantive analysis or edits.
2. Read its complete `SKILL.md` and the references it routes to for the task.
3. Follow its required audit workflow and finding format.
4. Treat the current working-tree implementation as authoritative unless the task names another revision.
5. Complete its pre-change audit before implementation.
6. Complete its post-change lifecycle audit before describing a guarantee as implemented.

Do not substitute documentation, model consensus, or passing focused tests for production-path analysis.

For unrelated repository work, use the auditor only when the task enters its stated scope.
