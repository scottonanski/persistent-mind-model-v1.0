# Work register — contract draft, revision 8 (UNAPPROVED)

Status: design draft only. Selects no policy, authorizes no implementation,
asserts no guarantee state for any real PMM item, places no file, publishes no
R17 finding.

Drafted against clean local `main` at
`83ec4dcea6ea9812e36706531427560b63eeead3`. That revision is **unpublished**:
`origin/main` remains at `82df03bcf971401305543df9e4e94a1c90cb00f0`, divergence
`origin/main...main = 0 1`.

Revision 8 resolves the four blockers against revision 7 and completes the
section renumbering. No revision 4–7 policy decision is reopened. Changes are
enumerated in §14.

## 1. Authority model

The register is a **projection of workflow metadata**. It is never authority for
whether a guarantee is true.

### 1.1 Field ownership

Revision 7's table assigned `evidence_status` and `assessment_status` to both
Audit and Register. The contradiction was real: those fields have
**register-owned sentinel values** and **audit-owned attested values**, and the
table did not distinguish them.

| Field | Owner | Canonical location |
|---|---|---|
| `evidence_status = "recorded"` | **Register** (sentinel) | Register — no attestation exists or is permitted |
| `evidence_status = "audited"` | **Audit** (copy) | Evidence attestation (§4.2) |
| `guarantee` while `evidence_status = "recorded"` | **Register** (provisional) | Register, grounded by `[item.source]` |
| `guarantee` while `evidence_status = "audited"` | **Audit** (copy) | Evidence attestation |
| `evidence.audit_revision` | **Audit** (copy) | Evidence attestation |
| `assessment_status = "unassessed"` | **Register** (sentinel) | Register — no attestation exists or is permitted |
| `assessment_status ∈ {holds, under_renewed_audit, regressed, superseded}` | **Audit** (copy) | Assessment attestation |
| `assessment.audit_revision`, `superseded_by` | **Audit** (copy) | Assessment attestation |
| `authorization.actor`, `.scope`, `.revision`, `.date` | **Authorizing human** (copy) | Authorization attestation (§4.6) |
| `[item.source]` fields | **Register** (referential metadata) | Register — grounding only, never evidence (§5.3) |
| `id`, `title`, `implementation_decision_status`, `implementation_authorization_status`, `delivery_status`, `hold_status`, `next_gate`, `notes`, hold fields, `[item.implementation]`, `[item.verification]` | **Register** | The structured register file |
| Narrative reasoning, findings, deferrals, policy questions | **Roadmap** | `pmm-improvement-progress.md` |

**Sentinel rule.** A sentinel value asserts the *absence* of an audit
conclusion. It is register-owned precisely because there is nothing to copy, and
its corresponding attestation block is forbidden (§5.4). Every non-sentinel
value is a copy and is subject to three-way equality (§4.3).

The generated view renders provisional rows as *provisional — unattested*.

### 1.2 Disagreement rule

If the register and its attestations disagree on any copied field, validation
**fails**. Neither side silently wins; reconciliation is a human act. Nothing is
ever parsed out of prose to populate a field.

## 2. Status model

| Field | Values |
|---|---|
| `evidence_status` | `recorded` \| `audited` |
| `implementation_decision_status` | `unselected` \| `selected` \| `withdrawn` |
| `implementation_authorization_status` | `none` \| `requested` \| `approved` \| `revoked` |
| `delivery_status` | `not_started` \| `in_progress` \| `implemented` \| `verified` \| `published` |
| `hold_status` | `active` \| `inactive` |
| `assessment_status` | `unassessed` \| `holds` \| `under_renewed_audit` \| `regressed` \| `superseded` |

### 2.1 `assessment_status` constraints

- Any value except `unassessed` requires a complete `[item.assessment]` block
  and an assessment attestation.
- `holds` means **"holds within the cited audit scope at the cited revision."**
  Never timeless truth; rendered with its revision attached, never bare.
- `superseded` requires `superseded_by` naming an item ID present in the
  register.
- `regressed` preserves the earlier `delivery_status` and `[item.implementation]`
  — enforced by §2.10.
- Any value except `unassessed` requires
  `delivery_status ∈ {implemented, verified, published}`.
- Never inferred from Git, tests, or delivery state (§10).

### 2.2 Static invariants

- `implementation_decision_status = selected` requires `evidence_status = audited`.
- `implementation_authorization_status = approved` requires
  `implementation_decision_status = selected`.
- `delivery_status ≠ not_started` requires
  `implementation_authorization_status ∈ {approved, revoked}`.
- `implementation_decision_status = withdrawn` requires
  `delivery_status = not_started` and `notes`.
- `delivery_status = verified` requires a populated `[item.verification]` block.
- `delivery_status = published` and `assessment_status = regressed` may coexist.
- `hold_status = active` requires `hold_reason` and `hold_reference`.
- Conditional sub-table presence per §5.4.

**Current-state-only predicate, listed separately because it is a Git fact:**

- `delivery_status = published` requires `impl_commit` contained in
  `baseline_published` (§7).

This predicate is **excluded from historical static validation** (§8.6). It
depends on `baseline_published` equalling today's `origin/main`, so a past
register version would legitimately fail it. Revision 7 placed it among the
static invariants while excluding Git facts from history — the contradiction is
resolved by classifying it here as current-state Git validation.

Approval is a *transition* requirement, not a static one: the static invariant
admits `revoked`, so a row delivered under approval and later revoked validates
and simply cannot advance.

### 2.3 Predecessor selection, creation, and deletion

**Predecessor, working-tree check.** `docs/work-register.toml` as committed at
`HEAD`, compared against the working-tree file, matched by `id`.

**Predecessor, historical check.** Each register-changing commit's version
compared against the version at that commit's **first parent** (§8.6).

**Creation.** A new row must satisfy every static invariant (§2.2) and, in the
working-tree check, every reference check (§8.4, §8.5). No adjacency constraint
and **no preservation predicate** applies at creation (§2.11). A row created in
any state other than the minimal state (`recorded` / `unselected` / `none` /
`not_started` / `unassessed`, hold either) **requires non-empty `notes`
recording the backfill basis**.

**Deletion is forbidden.** An `id` present in the predecessor must be present in
the successor. Retirement is `withdrawn` or `superseded`, never removal.

**ID replacement is forbidden.** `id` is immutable; renaming is a deletion plus
a creation and is rejected as such. `title` is mutable.

**Unchanged values are not transitions.** Adjacency tables (§2.6) are consulted
only for fields whose value **differs** from the predecessor.

The one case where an unchanged status value still constitutes work: if
`evidence_status` remains `audited` while `[item.evidence].audit_revision`
changes, that is a **re-audit**, requiring a new attestation, pin, and digest,
validated as the `audited → audited` edge.

### 2.4 Delivery edge classification

**Forward edges** — `not_started → in_progress`, `in_progress → implemented`,
`implemented → verified`, `verified → published`. Require
`implementation_authorization_status = approved` in the successor **and**
`hold_status = inactive` in both predecessor and successor.

**Retreat edges** — `in_progress → not_started`, `implemented → in_progress`,
`verified → implemented`. Permitted under any authorization state including
`revoked`, and while `hold_status = active`, because they record retreat rather
than progress; requiring approval to record that verification was invalidated
would suppress a factual correction. They require fresh `notes` (§2.9).

**Simultaneous hold clearing and advancement is forbidden.**

### 2.5 Real rows may be seeded unattested — decided

Real rows may be seeded at `evidence_status = recorded` without an attestation.
The two-gate sequence (§11) applies to **promotion to `audited`**, not to a
row's existence.

Rationale, stated without classifying any real item: a register that admitted
only audited rows could not represent candidates that have been written up but
not yet audited, and such candidates are the ordinary case in this repository's
roadmap. Requiring attestation for existence would exclude most of what the
register exists to track.

A `recorded` row requires `[item.source]` (§5.3), a resolvable reference to
where the finding is written — referential grounding, **not** attestation. No
equality, digest, or narrative check applies.

### 2.6 Adjacency tables

Consulted only for changed values (§2.3). Any pair not listed is blocking.

**`evidence_status`**

| From | To |
|---|---|
| `recorded` | `audited` |
| `audited` | `audited` (re-audit at a new `audit_revision`) |

**`implementation_decision_status`**

| From | To |
|---|---|
| `unselected` | `selected`, `withdrawn` |
| `selected` | `unselected` (only if `delivery_status = not_started`), `withdrawn` (only if `delivery_status = not_started`) |
| `withdrawn` | `unselected` (reopening; requires fresh `notes`) |

**`implementation_authorization_status`**

| From | To |
|---|---|
| `none` | `requested`, `approved` |
| `requested` | `approved`, `none` (declined) |
| `approved` | `revoked` |
| `revoked` | `requested`, `approved` |

**`delivery_status`**

| From | To | Class |
|---|---|---|
| `not_started` | `in_progress` | forward |
| `in_progress` | `implemented` | forward |
| `in_progress` | `not_started` | retreat |
| `implemented` | `verified` | forward |
| `implemented` | `in_progress` | retreat |
| `verified` | `published` | forward |
| `verified` | `implemented` | retreat |
| `published` | — | **terminal** |

**`hold_status`**

| From | To |
|---|---|
| `active` | `inactive` |
| `inactive` | `active` |

**`assessment_status`**

| From | To |
|---|---|
| `unassessed` | `holds`, `under_renewed_audit`, `regressed`, `superseded` |
| `holds` | `under_renewed_audit`, `regressed`, `superseded` |
| `under_renewed_audit` | `holds`, `regressed`, `superseded` |
| `regressed` | `under_renewed_audit`, `holds`, `superseded` |
| `superseded` | — **terminal** |

### 2.7 Transition constraints

- Forward delivery edges: approved authorization and inactive hold (§2.4).
- Retreat delivery edges: fresh `notes`; no authorization or hold constraint.
- `implementation_authorization_status → approved` forbidden while
  `hold_status = active`.
- An active hold does not block advancing `evidence_status`, changing
  `assessment_status`, withdrawing, or clearing the hold.
- `selected → unselected` requires `delivery_status = not_started`.
- No simultaneous hold-clear plus forward delivery edge.
- Preservation predicates per §2.10, subject to §2.11.

### 2.8 `next_gate` emptiness

Empty **only** when settled:

- `implementation_decision_status = withdrawn` with `notes` populated — which by
  §2.2 implies `delivery_status = not_started` and therefore
  `assessment_status = unassessed`; **or**
- `delivery_status = published` **and** `assessment_status ∈ {holds, superseded}`
  **and** `hold_status = inactive` **and**
  `implementation_authorization_status ≠ revoked`.

### 2.9 Fresh-notes requirement

`notes` must be **non-empty AND different from the predecessor's `notes`** for:

| Transition | Reason recorded |
|---|---|
| Any retreat delivery edge (§2.4) | why work retreated |
| `implementation_authorization_status: approved → revoked` | why authorization was withdrawn |
| `implementation_decision_status: withdrawn → unselected` | why the item reopened |
| `implementation_decision_status: → withdrawn` | why the item was abandoned |
| `implementation_decision_status: selected → unselected` | why selection was reversed |
| Creation at any non-minimal state (§2.3) | the backfill basis |

### 2.10 Preservation predicates

Predecessor-equality rules, blocking on violation. **Subject to §2.11.**

| Predicate | Rule |
|---|---|
| **Revocation freezes the grant** | If `implementation_authorization_status = revoked` in the successor, every field of `[item.authorization]` must equal the predecessor's. Re-authorization (`revoked → approved` or `→ requested`) may write a new grant. |
| **Regression freezes delivery** | If `assessment_status` becomes or remains `regressed`, `delivery_status` and every field of `[item.implementation]` must equal the predecessor's. |
| **Publication freezes implementation** | Once `delivery_status = published`, `[item.implementation]` is immutable for all later updates. |
| **Reassessment cannot touch evidence** | If any field of `[item.assessment]` or `assessment_status` changes, every field of `[item.evidence]` must equal the predecessor's. |
| **Re-audit cannot touch assessment** | If any field of `[item.evidence]` changes, every field of `[item.assessment]` must equal the predecessor's. |
| **Mutual exclusion** | `[item.evidence]` and `[item.assessment]` may not both change in a single register update. |

### 2.11 Preservation predicates do not apply at creation

Every predicate in §2.10 is a comparison against a predecessor. A created row
has none, so **§2.10 applies only to IDs present in both predecessor and
successor**. Revision 7 left backfilled `revoked` or `regressed` rows requiring
equality with a nonexistent predecessor, which no register could satisfy.

A backfilled creation is instead constrained by:

- every static invariant (§2.2), including the conditional-presence table — a
  created `revoked` row therefore carries `[item.authorization]`, and a created
  `regressed` row carries `[item.implementation]` and `[item.verification]`,
  because presence is required by state rather than by preservation;
- every reference check (§8.4, §8.5) in the working-tree check;
- non-empty `notes` recording the backfill basis (§2.3, §2.9).

Backfilled state is therefore grounded by present references rather than by a
history the register never observed. That limit is inherent: the register cannot
validate transitions that occurred before it existed.

## 3. Format

TOML, with `"tomli>=2; python_version < '3.11'"` added to the existing
`[project.optional-dependencies] dev` group at
[pyproject.toml:18-23](pyproject.toml#L18-L23).

`scripts/work_register.py` imports `tomllib` on 3.11+ with a `tomli` fallback;
under 3.9/3.10 without the dev environment it exits with a clear error naming
the missing package and its dependency group, never a bare traceback.

## 4. Attestations

### 4.1 Why prose digests cannot do this

A digest over an audit section detects textual change in that section. It cannot
detect a register-only edit, and read from an immutable pinned revision it
detects nothing later. Disagreement detection requires comparing **exact
structured values**.

### 4.2 Three attestation kinds

````markdown
```toml
# work-register attestation: evidence
id              = "SYNTHETIC-1"
guarantee       = "One falsifiable sentence."
audit_revision  = "<full SHA>"
evidence_status = "audited"
```
````

````markdown
```toml
# work-register attestation: assessment
id                        = "SYNTHETIC-1"
assessment_status         = "regressed"
assessment_audit_revision = "<full SHA>"
# superseded_by           = "SYNTHETIC-2"   # required iff status = superseded
```
````

Authorization attestation: §4.6.

**Parser requirements.** Under a referenced heading there must be **exactly one**
correctly labelled block of the expected kind. Zero, duplicates, or a mislabelled
block is blocking. The `# work-register attestation: <kind>` label is
contractual.

### 4.3 Three-way equality — live, pinned, and register

All three blocking, per attestation:

1. **Live equality** — decoded from the **working tree** at its anchor, equals
   the register's copied fields exactly.
2. **Pinned equality** — decoded from **`record_revision`**, equals the
   register's copied fields exactly.
3. **Pin integrity** — block text at `record_revision` hashes to
   `attestation_digest`.

**Consequence, intended.** Changing a guarantee requires the new attestation to
be committed first, so a `record_revision` containing it exists, before the
register row can be updated. That is the two-gate sequence of §11, enforced
mechanically.

### 4.4 Per-kind equality mapping

Every attestation must carry `id`, and **`attestation.id` must equal `item.id`**
— checked before any other comparison.

| Kind | Attestation field | Register field |
|---|---|---|
| evidence | `id` | `item.id` |
| evidence | `guarantee` | `item.guarantee` |
| evidence | `audit_revision` | `item.evidence.audit_revision` |
| evidence | `evidence_status` | `item.evidence_status` |
| assessment | `id` | `item.id` |
| assessment | `assessment_status` | `item.assessment_status` |
| assessment | `assessment_audit_revision` | `item.assessment.audit_revision` |
| assessment | `superseded_by` | `item.assessment.superseded_by` |
| authorization | `id` | `item.id` |
| authorization | `actor` | `item.authorization.actor` |
| authorization | `scope` | `item.authorization.scope` |
| authorization | `revision` | `item.authorization.revision` |
| authorization | `date` | `item.authorization.date` |

Exact string equality on decoded TOML values. Fields present in an attestation
but absent from this mapping are blocking; the attestation schema is closed.

### 4.5 Attestation independence

Enforced by §2.10, not merely asserted.

### 4.6 Authorization attestation

````markdown
```toml
# work-register attestation: authorization
id       = "SYNTHETIC-1"
actor    = "<approving human>"
scope    = "<exact authorized scope, verbatim>"
revision = "<full SHA the authorization was issued against>"
date     = "YYYY-MM-DD"
```
````

- **`record_kind = "repository"`** — attestation resolvable at
  `[item.authorization].record_anchor` in `record_file` at `record_revision`,
  subject to §4.3. Blocking on failure.
- **`record_kind = "external"`** — no repository attestation.
  `external_reference` must match §5.5. Nothing else is checked.

**Stated plainly, for both kinds.** An authorization attestation is an
*attributable, mechanically consistent claim that an authorization was granted*.
It is not proof that the named actor granted it. There is no signature mechanism
in this repository and adding one is out of scope.

### 4.7 Narrative reconciliation — evidence and assessment only

`reconciled_narrative_digest` exists on `[item.evidence]` and `[item.assessment]`
and **not** on `[item.authorization]`: an authorization record *is* its
attestation and has no surrounding narrative.

- hash the **current working-tree** section under the anchor, **excluding all
  attestation blocks**;
- compare against `reconciled_narrative_digest`;
- on mismatch, **fail** until a human reviews and updates the digest.

The failure message reads only **"narrative changed since reconciliation"**.

### 4.8 Attestation precondition — scoped to promotion

**No row may reach `evidence_status = audited` until its audit record contains
an evidence attestation**, following §11. Per §2.5 this gates promotion, not
existence. Attestation authoring is audit work under
`$pmm-development-auditor`.

## 5. Record schema

### 5.1 Top level

```toml
schema_version     = 1
base_revision      = "<full SHA that predates the register>"   # §8.6
baseline_local     = "83ec4dcea6ea9812e36706531427560b63eeead3"
baseline_published = "82df03bcf971401305543df9e4e94a1c90cb00f0"   # must equal local origin/main at validation time (§7)
```

**`base_revision` replaces revision 7's `register_origin_revision`,** which was
impossible to seed: it required the file to contain the SHA of the commit
introducing that same file, and embedding a SHA changes the commit's SHA. A
placeholder-first bootstrap failed too, because §8.6 schema-validates the first
version.

`base_revision` names a **pre-existing** revision — the commit the register was
authored against, which is the introducing commit's first parent. It is known
before the register is written, so it is seedable. The validator derives the
introducing commit from history and asserts consistency (§8.6).

### 5.2 Item

```toml
[[item]]
id        = "SYNTHETIC-1"
title     = "Example row"
guarantee = """One falsifiable sentence; provisional unless evidence_status = audited (§1.1)."""

evidence_status                     = "audited"
implementation_decision_status      = "selected"
implementation_authorization_status = "approved"
delivery_status                     = "published"
hold_status                         = "inactive"
assessment_status                   = "holds"

next_gate = ""            # empty permitted only under §2.8
notes     = ""
# hold_reason    = "..."  # required iff hold_status = active
# hold_reference = "..."  # required iff hold_status = active

[item.source]             # required iff evidence_status = recorded; forbidden iff audited
record_file     = "pmm-improvement-progress.md"
record_anchor   = "synthetic-1-finding"
record_revision = "<full SHA containing that record>"

[item.evidence]           # required iff evidence_status = audited; forbidden otherwise
audit_revision              = "<full SHA the audit ran against>"
record_file                 = "pmm-improvement-progress.md"
record_anchor               = "synthetic-1-example-guarantee"
record_revision             = "<full SHA containing that attestation>"
attestation_digest          = "sha256:..."
reconciled_narrative_digest = "sha256:..."

[item.assessment]         # required iff assessment_status != unassessed; forbidden otherwise
audit_revision              = "<full SHA>"
record_file                 = "pmm-improvement-progress.md"
record_anchor               = "synthetic-1-reassessment"
record_revision             = "<full SHA containing that attestation>"
attestation_digest          = "sha256:..."
reconciled_narrative_digest = "sha256:..."
# superseded_by             = "SYNTHETIC-2"

[item.authorization]      # required iff implementation_authorization_status in {approved, revoked}; forbidden otherwise
actor       = "<approving human>"
scope       = "<exact authorized scope, verbatim>"
revision    = "<full SHA>"
date        = "YYYY-MM-DD"
record_kind = "repository"          # "repository" | "external"
# --- required iff record_kind = "repository"; forbidden iff "external" ---
record_file        = "docs/authorizations.md"
record_anchor      = "synthetic-1-authorization"
record_revision    = "<full SHA containing that attestation>"
attestation_digest = "sha256:..."
# --- required iff record_kind = "external"; forbidden iff "repository" ---
# external_reference = "conversation:2026-07-26-placement-review"   # §5.5

[item.implementation]     # required iff delivery_status in {implemented, verified, published}; optional iff in_progress; forbidden iff not_started
impl_commit       = "<full 40-char SHA>"
allowed_paths     = ["pmm/core/example.py"]
required_paths    = ["pmm/core/example.py"]
# comparison_parent = "<full SHA>"   # required iff impl_commit has >=2 parents (§6)

[item.verification]       # required iff delivery_status in {verified, published}; forbidden otherwise
revision             = "<full SHA>"
worktree_clean       = true
environment          = "<python version, OS, provider/live-run status>"
commands             = ["pytest tests/test_example.py -q"]
results              = "<counts and outcomes>"
checks_not_performed = ["no full suite", "no live-provider run"]   # §5.6
```

### 5.3 `[item.source]` — grounding for unattested rows

Required exactly when `evidence_status = recorded`; forbidden once `audited`.
The validator checks that `record_revision` exists, is an ancestor of
`baseline_local`, and that `record_anchor` resolves to a heading in
`record_file` at that revision.

**No attestation, equality, digest, or narrative check applies.** Referential
grounding only: the finding is written somewhere identifiable, nothing about it
has been audited.

### 5.4 Conditional block presence

| Block | Required when | Forbidden when |
|---|---|---|
| `[item.source]` | `evidence_status = recorded` | `evidence_status = audited` |
| `[item.evidence]` | `evidence_status = audited` | `evidence_status = recorded` |
| `[item.assessment]` | `assessment_status ≠ unassessed` | `assessment_status = unassessed` |
| `[item.authorization]` | `implementation_authorization_status ∈ {approved, revoked}` | `∈ {none, requested}` |
| `[item.implementation]` | `delivery_status ∈ {implemented, verified, published}` | `delivery_status = not_started` |
| `[item.verification]` | `delivery_status ∈ {verified, published}` | `delivery_status ∈ {not_started, in_progress, implemented}` |

`[item.implementation]` is optional at `in_progress`. Preservation across
transitions is governed by §2.10 and §2.11, not by this table.

### 5.5 `external_reference` syntax

`^(conversation|email|ticket|document):[^\s]{1,200}$`

Syntax only. The validator cannot and does not check that the referenced record
exists, is accessible, or says what the row claims (§4.6).

### 5.6 `checks_not_performed`

An array of at least one non-empty string; never empty, never omitted. To claim
nothing was skipped, the array must contain an explicit positive statement, for
example `["none: full suite, focused tests, and live-provider run all
performed"]`. Silence about what was not checked is what this field exists to
prevent.

### 5.7 Stable anchors

`record_anchor` is a stable slug resolved by scanning headings, never a line
offset. Line anchors drift on every insertion — this session produced two such
drifts, including my miscitation of the freeze list as the auditor mandate.

## 6. Implementation scope validation

**Applies only to `impl_commit`.**

- `allowed_paths` — the commit must touch **nothing outside** this set.
- `required_paths` — the commit must touch **every** path here.
- `required_paths ⊆ allowed_paths`.

| Parents | Rule |
|---|---|
| 0 (root commit) | **Rejected.** If one ever must be cited, this contract requires amendment. |
| 1 | `comparison_parent` forbidden; the single parent is used. |
| ≥2 | `comparison_parent` required; validator asserts it equals `git rev-parse <impl_commit>^1`; introduced paths are `git diff --name-only <comparison_parent> <impl_commit>`. |

This checks publication scope; it does not prove implementation correctness.

## 7. Publication semantics

- `baseline_published` **must equal the locally known `origin/main`** at
  validation time, compared against `git rev-parse refs/remotes/origin/main`.
- `delivery_status = published` means **locally verified remote-tracking
  containment**.
- The validator performs **no network fetch**. A stale `origin/main` yields a
  stale conclusion; the generated view states the observation revision beside
  every published row.
- Publication is recorded by a **subsequent register update**, never in the same
  commit that implements the change.

## 8. Mechanical validation

**8.1 Schema** — field types; enums valid; SHAs full 40-char; conditional block
presence per §5.4; `next_gate` emptiness per §2.8; `required_paths ⊆
allowed_paths`; `external_reference` per §5.5; `checks_not_performed` per §5.6;
closed attestation schema per §4.4.

**8.2 Static invariants** — §2.2, excluding the current-state-only publication
predicate when validating history.

**8.3 Transitions** — adjacency per §2.6 for changed values only; constraints per
§2.7; delivery edge class per §2.4; fresh notes per §2.9; preservation
predicates per §2.10 subject to §2.11.

**8.4 Git facts.** Path constraints apply to `impl_commit` alone.

| Reference | Existence | Ancestry | Path constraints | Other |
|---|---|---|---|---|
| `implementation.impl_commit` | yes | yes | **yes** (§6) | parent rules §6 |
| `verification.revision` | yes | yes | no | — |
| `source.record_revision` | yes | yes | no | anchor resolvable; §5.3 |
| `evidence.audit_revision` | yes | yes | no | — |
| `evidence.record_revision` | yes | yes | no | anchor + attestation resolvable here |
| `assessment.audit_revision` | yes | yes | no | — |
| `assessment.record_revision` | yes | yes | no | anchor + attestation resolvable here |
| `authorization.revision` | yes | yes | no | — |
| `authorization.record_revision` | yes | yes | no | required iff `record_kind = "repository"` |

Ancestry is against `baseline_published` for `delivery_status = published` (§7),
otherwise `baseline_local`.

**8.5 Attestations and narrative**

| Check | Applies to | Reads from | Severity |
|---|---|---|---|
| `attestation.id == item.id` | all present kinds | working tree + pin | blocking |
| Anchor resolves to a heading | all present kinds | working tree | blocking |
| Exactly one correctly labelled block of the expected kind | all present kinds | working tree | blocking |
| Live equality per §4.4 | all present kinds | working tree | blocking |
| Pinned equality per §4.4 | all present kinds | `record_revision` | blocking |
| Pin integrity — hash == `attestation_digest` | all present kinds | `record_revision` | blocking |
| Narrative hash (attestations excluded) | evidence and assessment only | working tree | blocking |

### 8.6 Committed-history validation

`--check` validates **both** the `HEAD → working tree` transition, when the file
differs, **and** every committed register transition.

**Mainline traversal.** Revision 7 used `git log --reverse -- <path>`, whose
consecutive results need not be parent and child when branches or merges exist.
Corrected to explicit first-parent mainline semantics:

1. Walk `git rev-list --first-parent --reverse <base_revision>..HEAD`.
2. For each commit `C` in that sequence, load the register file at `C` and at
   `C^1`.
3. If the two differ, validate that pair as one transition, predecessor `C^1`,
   successor `C`.
4. The first commit where the file exists at `C` but not at `C^1` is the
   **introducing commit**; its rows are validated as creations, and the
   validator asserts `C^1 == base_revision`. This is the consistency check that
   replaces the impossible self-referential pin (§5.1).

**Merge semantics, stated as a limit.** A merge commit on the mainline is
validated as a **single aggregate transition** from its first-parent version to
the merged result, which matches how this repository publishes branch work.
Intermediate register states that existed only on a side branch are **not**
validated. A side-branch sequence passing through an illegal intermediate state
but landing on a legal result is therefore not detected. This is a deliberate
scope limit, not an oversight.

**Historical scope limit.** Historical validation applies **schema (§8.1),
static invariants (§8.2) excluding the publication predicate (§2.2), and
transitions (§8.3) only**. It does not apply Git-fact (§8.4), attestation, or
narrative (§8.5) checks, which are defined against present state. Reference
integrity is guaranteed for the current state and **not** retroactively for
every past state.

**Modes.** `--check` runs the full sequence and is the authoritative form.
`--check --since <rev>` validates a bounded range and **prints the range it
covered**, so a partial run cannot be mistaken for a full one.

**What §6, §7, and §8.4 do and do not establish.** They establish that a cited
commit exists, sits on the declared baseline, touched exactly the declared
scope, and — for published rows — is contained in the locally observed
`origin/main`. They do **not** establish that it implements the guarantee.

## 9. Generation

`scripts/work_register.py` renders `docs/work-register.md` from
`docs/work-register.toml`. The generated file carries a
`<!-- generated; do not edit -->` header naming its source, states that it is a
workflow projection with no authority over guarantee truth, marks provisional
unattested rows (§1.1), renders `holds` with its audit revision attached, labels
externally-attested authorizations, and prints the `origin/main` observation
revision beside published rows.

## 10. Non-inference boundary

Tooling never derives, from commit messages, diffs, test output, or prose:

- whether a guarantee holds, has regressed, or is superseded;
- whether verification was sufficient;
- what any status field should be;
- what a guarantee sentence should say;
- whether a narrative change means the audit conclusion changed;
- whether an authorization was genuinely granted.

Automation checks **form, references, and exact-value equality**. It never
checks **truth**. A register passing every check can still be wrong about what
the code does, and the generated view must say so.

## 11. Attestation and seeding — two gates, two commits

1. **Gate 1** — authorize and commit the audit-record attestation as its own
   documentation change.
2. **Review** — review that committed record; it now has a fixed SHA.
3. **Gate 2** — separately authorize and commit the register row or promotion,
   pinned to that `record_revision`.

Applies to promotion to `audited`, to assessment attestations, and to repository
authorization attestations. §4.3 pinned equality makes the ordering mechanical.
Consistent with [CONTRIBUTING.md:223](CONTRIBUTING.md#L223), "Keep one logical
change per commit."

## 12. Enforcement — invocation-only, version 1

No CI, no hooks. The repository has **no `.github` directory**, verified at
`83ec4dc`.

`scripts/work_register.py --check` regenerates the view, diffs against the
committed output, runs §8 including committed-history validation (§8.6), and
exits non-zero on any difference or blocking failure.

**The documented pre-publication procedure is
[CONTRIBUTING.md](CONTRIBUTING.md#L222) §7, "Commit and publication
discipline."**

> Register validation is implemented only when explicitly invoked.

## 13. Placement scope — design approved, placement not authorized

| Artifact | Path | New or edited |
|---|---|---|
| Contract | `docs/work-register-contract.md` | new |
| Structured source | `docs/work-register.toml` | new |
| Generated view | `docs/work-register.md` | new |
| Validator/renderer | `scripts/work_register.py` | new |
| Tests | `tests/test_work_register.py` | new |
| Dev dependency `tomli` | `pyproject.toml` | **edited**, dev group, lines 18-23 |
| Pre-publication procedure | `CONTRIBUTING.md` | **edited**, §7 |

A placement authorization must explicitly name all seven of:

1. the seven repository paths above, distinguishing new from edited;
2. the conditional `tomli>=2; python_version < "3.11"` dev dependency;
3. synthetic fixtures only;
4. no real PMM rows and no R17 publication;
5. invocation-only enforcement;
6. documentation-governance/tooling scope only;
7. no runtime changes, hooks, CI, push, or publication.

**R17.** Its audit publication is a separate change. The findings recorded in
conversation — the configured-parameter mismatch making non-default digests
factually wrong, the source comment admitting the empty-candidate case cannot
verify anything before falling through to OK, and the nonfunctional shadowed `N`
as a maintenance hazard — must become their own reviewed audit record, with an
evidence attestation, before any promotion to `audited`.

**Routing.** This contract, the schema, validator semantics, transition rules,
attestation format, and every real guarantee-bearing row fall under
`$pmm-development-auditor` per `AGENTS.md:9`.

## 14. Changes from revision 7

1. **`register_origin_revision` replaced by `base_revision` (§5.1, §8.6).** The
   old field required a file to contain the SHA of the commit introducing it,
   which is impossible; the placeholder bootstrap also failed schema validation.
   `base_revision` names a pre-existing revision, is seedable, and the validator
   derives the introducing commit from history and asserts
   `introducing^1 == base_revision`.
2. **First-parent mainline traversal defined (§8.6).** `git rev-list
   --first-parent --reverse <base_revision>..HEAD`, comparing each register
   version against its first-parent version. Merge commits validate as one
   aggregate transition; side-branch intermediate states are explicitly out of
   scope.
3. **Publication predicate reclassified (§2.2, §8.2).** Moved out of the
   history-validated static invariants and marked current-state Git validation,
   resolving the contradiction between "all static invariants" and "no Git facts"
   in historical validation.
4. **Sentinel ownership defined (§1.1).** `recorded` and `unassessed` are
   register-owned sentinels asserting the absence of an audit conclusion, with
   their attestation blocks forbidden; `audited` and non-`unassessed` values are
   audit-owned copies subject to three-way equality; `[item.source]` is
   register-owned referential metadata.
5. **Creation semantics for preservation added (§2.11).** §2.10 applies only to
   IDs present in both predecessor and successor. Backfilled creation is
   constrained by static invariants, conditional presence, reference checks, and
   backfill notes instead, with the inherent limit stated.

Also: reserved §11 collapsed and all sections renumbered; the §2.1 pointer to
the non-inference boundary now correctly resolves to §10; the §2.5 rationale
rephrased so it no longer classifies named real candidates, consistent with §15.

Retained unchanged: every revision 4–7 policy decision, the seven placement
paths, synthetic-only fixtures, invocation-only enforcement, and the exclusions
on real rows, R17 publication, runtime changes, CI, hooks, push, and
publication.

## 15. What this draft does not do

No generator, register file, test, hook, attestation, or dependency change is
written. No item state is asserted for any real PMM item. No file is placed in
the repository. No R17 finding is published. All example rows and identifiers
are synthetic.
