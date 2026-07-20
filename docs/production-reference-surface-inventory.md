# Production Cross-Event and Cross-Entity Reference Inventory

- **Audit date:** 2026-07-20
- **Repository revision:** `a615af55e9d8a4701a35f23d99c4f2f850229ca0` (`main`)
- **Prior inventory revision:** `ef63a8f59e32b35594261e98e4befb5fa78f3dc2`
- **Audit method:** PMM Development Auditor, current production paths first
- **Change scope:** Documentation only. This inventory does not select policy or authorize runtime changes.

## Repository and evidence state

At the audit boundary, local `main`, `HEAD`, and `origin/main` resolved to `a615af5` with divergence `0 0`; the tracked and untracked working tree was clean. The local full suite passed `468` tests in `23.02` seconds, and `git diff --check` passed. These are local audit observations, not GitHub Actions results.

The prior inventory was headed at `ef63a8f` and retained older `427`- and `431`-test observations. It already incorporated the subsequently authorized R08 documentation, but it predated C01, C02 stages 1–3, and the current writer/projection control plane. This replacement refreshes the inventory against `a615af5`; it does not convert any open question into policy.

## Scope, method, and limits

This inventory includes serialized fields and active control structures that production code uses relationally to affect canonical events, deterministic projections, identity, commitments, concept state, graph relationships, fast reconstruction, future retrieval, or authority to write and promote state.

The audit traced each surface through:

```text
producer or parser
  -> validation or rejection
  -> historical preservation
  -> canonical recording
  -> projection or retrieval
  -> authoritative promotion or mutation
```

“Every producer” means every in-repository production producer found by searching append sites, semantic extraction, control-table writes, projection registration, rebuilds, and retrieval consumers. External `GenerationProvider` implementations and programmatic `EventLog` callers are not a closed set. Public `EventLog.append` remains an alternate producer for accepted event kinds, but Stage 3 now requires live fenced writer authority for those writes.

Tests are evidence only for the paths and fixtures they exercise. Documentation, model output, real event IDs, graph edges, and passing focused tests do not independently establish semantic adequacy.

## Explicit exclusions

The following recorded identifiers remain outside the numbered inventory because no production relational dereferencer or promotion consumer was found:

- `claim_from_text.content.source_event_id`
- `outcome_observation.content.evidence_event_ids` and `commitment_id`
- coherence-check comparison IDs
- `reflection.meta.meta_summary.about_event`
- C02 prompt telemetry `prior_conversation_event_ids` and `prior_conversation_deduplicated_event_ids`

The C02 telemetry fields are canonical metadata, but they are content-free audit measurements and no later production path dereferences them. The actual prior-pair relationship is included under R01 because it is derived from canonical `about_event`, projected through `MemeGraph`, dereferenced from `EventLog`, and rendered into the current prompt.

## Changes since `ef63a8f`

| Change | Reference-surface effect |
|---|---|
| R08, `adf3e57` | Made commitment closure an atomic, idempotent transition from one exact open event. Generic close append delegates to the same boundary. |
| C01, `e2caabf` | Made the shared `MemeGraph` reconstruct complete tracked history before production consumption. This strengthened reconstruction of R01, R02, R06, R07, and R08 relationships without strengthening their field semantics. |
| C02 stages 1–2, `5570150` | Added an indexed R01 consumer: one prior completed managed pair is graph-selected, exactly dereferenced, and rendered as bounded non-evidentiary context. |
| C02 Stage 3, `69cbe30` | Added database identity, writer leases and fencing, transactional predecessor selection, required projection watermarks, durable projection health, and fail-closed delivery. |
| `9d446fc` and `a615af5` | Documentation-only updates. They changed no runtime or test files. |

No R01–R24 surface was removed. R01, R02, R06–R08, R10–R17, and R22 gained changed consumers, stronger delivery/governance, or a corrected classification. R25–R27 are new Stage 3 control-plane surfaces. R28 existed before `ef63a8f` but was omitted from the earlier inventory; Stage 3 materially strengthened its production behavior.

## Current reference surfaces, producers, and consumers

### R01–R08: managed turns, evidence, identity, and commitments

| ID | Surface | Every in-repository production producer found | Validation, preservation, consumers, and promotion | Strongest supported conclusion |
|---|---|---|---|---|
| R01 | Protocol terminal `assistant_message` or `generation_failure`, `meta.{turn_protocol,about_event}` | `RuntimeLoop` success, transport failure, general failure, truncated output, and interrupted-turn recovery call `EventLog.append_terminal_outcome`; direct `EventLog.append` can write legacy or malformed protocol forms | Helper checks positive integer ID, outcome kind, content type, and one protocol-v1 terminal per integer `about_event`; it does not load the target. `MemeGraph` promotes a managed pair only when the target is an earlier protocol-v1 `user_message`. The renderer rechecks both exact canonical records before prompt use. Invalid direct records may remain canonical but are excluded from the managed-pair index. | Managed terminal uniqueness and conversational promotion are implemented and mandatory on the audited runtime path. General target existence/kind/order is not an append-wide guarantee. |
| R02 | `reflection.meta.about_event` | Runtime turn-delta reflection; direct append callers; other deterministic and autonomy reflection producers usually omit it | No dedicated validator. Required `MemeGraph` delivery creates `reflects_on` only when the target is already a tracked node. Missing or unresolved targets leave the reflection canonical and omit the edge. `IdentityManager` can use any reflection as an identity anchor independently of this link. | Optional and best-effort relationally. Projection delivery is mandatory; reference role and relevance are not. |
| R03 | Assistant JSON header `evidence_designations[] = {event_id,supports}` | Model output through `SemanticExtractor` and `RuntimeLoop` | Validation runs only when the header contains the key. Positive IDs, nonempty `supports`, duplicate pairs, and current retrieval selection are checked all-or-nothing. Failure preserves the assistant and appends `validation_failure`; valid data is copied to assistant metadata. No later relational promoter was found. | Current-selection constrained when supplied; omission and empty lists remain accepted. |
| R04 | Claim `data.evidence_events[]` | Model `CLAIM:` lines through `RuntimeLoop`; direct validator callers are possible, but canonical managed claim production was found in the loop | Per parsed claim, the validator checks list shape, positive IDs, ledger existence, and current selection when the loop supplies `selection_ids`. Invalid claims are omitted and produce `validation_failure`; valid claims may be canonically recorded, concept-bound, retrieved, and consumed by identity/RSM paths. | Existence and current-turn availability are enforced only when evidence is declared on the managed path. Target kind, role, duplicates, cardinality, and semantic support remain unspecified. |
| R05 | Claim `event_existence.data.id` and `reference.data.id` | Model `CLAIM:` lines through `RuntimeLoop` | Both convert `id` with unguarded `int(...)` and check only ledger existence. Contrary to the prior inventory, current `reference` validation does not require the target to be a `claim` or current-turn selected. Valid claims receive the ordinary R04 promotion path; missing targets produce typed failure, while malformed scalar conversion can interrupt post-response processing. | Referential existence is checked when validation completes; target role/kind and total input normalization are not enforced. |
| R06 | Identity proposal/ratification token chain and `identity_adoption.meta.{proposal_event_id,anchor_event_id,anchor_kind,ratify_event_id}` | Model identity claims; `IdentityManager` scans canonical `claim` events with `validated:true` and emits adoption; direct forged validated claim metadata can enter the scan | Claim validation checks token/allowed fields. Manager checks proposal-before-anchor-before-ratification, anchor kind, same token, and one adoption per token. Required `MemeGraph` and `ConceptGraph` projections consume adoption. Anchor relevance, asserting actor, subject, predicate, object, and evidence role are absent. | Temporal/token structure is implemented; relational subject and anchor relevance remain unproven. Direct trusted validation metadata is a governance boundary. |
| R07 | `commitment_open.meta.cid` | `CommitmentManager.open_commitment`, `open_internal_goal`, runtime/autonomy producers through the manager, direct append | Manager paths call the event schema; direct append does not. Required Mirror and MemeGraph projections consume truthy CIDs. Context, lifetime memory, evaluators, and R08 closure use the resulting state. Duplicate opens for one CID remain canonical and replace the Mirror’s current open-map entry. | Basic manager-produced shape plus fresh projection is implemented. Repository-wide CID uniqueness and duplicate-open governance are not. |
| R08 | `commitment_close.meta.{cid,source,open_event_id}` | Assistant closures, autonomy stale-goal/gap-resolution/internal-goal closures through `CommitmentManager`; generic `EventLog.append(kind="commitment_close")` delegates to `append_commitment_close` | Under `BEGIN IMMEDIATE`, the helper requires nonempty CID/source, resolves the latest CID lifecycle event, closes only an open event, records exact `open_event_id`, and uses a unique index for one close per open. Unknown CID creates no manager event; generic append raises. Repeated close returns the existing ID. Required Mirror/MemeGraph projections consume the result; legacy close history retains CID fallback. | Implemented and mandatory across audited producers and generic append: exact open-state transition, ordering, source retention, linkage, and idempotence. Semantic fulfillment remains unresolved. |

### R09–R17: execution, concepts, external references, vectors, and retrieval

| ID | Surface | Every in-repository production producer found | Validation, preservation, consumers, and promotion | Strongest supported conclusion |
|---|---|---|---|---|
| R09 | Exec-bind config `{type:"exec_bind",cid,exec,params}` | Runtime idle-monitor commitment setup; direct config append | Router/config scans apply basic shape; `EventLog.has_exec_bind` compares CID; autonomy may suppress closing a matching commitment. No commitment existence/open-state check. Malformed records may be skipped while orphan binds remain canonical. | Operationally consumed but relationally ungoverned. |
| R10 | `concept_define.meta.supersedes` and token/version/concept-ID history | `seed_ctl_ontology`; `ConceptOpsCompiler` from assistant `concept_ops`; direct append | Helper checks basic definition shape; compiler/append do not invoke the standalone schema validator. Required ConceptGraph delivery projects truthy supersession without target existence, same-token lineage, ordering, version monotonicity, or cycle checks. Malformed records can be silently skipped inside the callback while its watermark advances. | Supersession is recorded and freshly projected, not governed. |
| R11 | `concept_alias.content.{from,to}` | `ConceptOpsCompiler`; direct append | Compiler/helper check basic token shape and inequality. Required ConceptGraph projects aliases. Direct malformed history is skipped; target definitions and cycles are not prevented at append. | Basic compiler structure is enforced; endpoint and cycle integrity are not. |
| R12 | `concept_relate.content.{from,to,relation}` | `ConceptOpsCompiler`; ontology seeding; direct append | Compiler/helper check shape and compiler exact-tuple deduplication. Required ConceptGraph projects even undefined endpoints. Relation registry, role, cardinality, and cycles are unchecked. | Structurally projected but relationally unproven. |
| R13 | `concept_bind_event` / `concept_bind_async` `{event_id,tokens,relation}` plus attribution metadata | Runtime active indexing and claim binding; compiler; Indexer; autonomy maintenance; binding-audit backfill; direct append | Every bind append invokes attribution validation, including assistant-kind dereference for `model_declared.origin_event_id`; legacy attribution remains allowed. Bound target existence/kind, token definition, relation role, and most origin IDs are not uniformly checked. Required ConceptGraph delivery can silently skip or partially project bad content. Bindings alter retrieval. | Attribution is partially enforced; target and relation integrity are not. |
| R14 | `concept_bind_thread` `{cid,tokens,relation}` plus attribution metadata | Runtime after commitment open; Indexer backfill; direct append | Same attribution boundary as R13. Required ConceptGraph retains concept-to-CID membership without checking CID existence/open state, token definition, relation role, or cardinality. Retrieval expands matching MemeGraph threads; unknown CIDs yield empty slices. | Freshly projected but entity-state and role constraints are unenforced. |
| R15 | `inter_ledger_ref` target `REF:<path>#<id>` plus `meta.{target_hash,verified}` | Model assistant JSON `refs` or `REF:` lines through `RuntimeLoop` | Parser opens the foreign ledger with read-only `EventLog`, loads the ID, and captures its hash. Missing/open errors produce canonical `verified:false`; malformed lines disappear. Later dedup, autonomy, and replay-narration paths read the record, but no foreign revalidation occurs. The new database UUID is not recorded. | Creation-time existence/hash is observed without ledger-identity, target-kind, role, trust, or later-integrity guarantees. |
| R16 | `embedding_add.content.event_id` | Runtime `ensure_embedding`; Indexer; autonomy maintenance; CLI/backfill; direct append | Normal producers use real events. Append/load does not validate target existence/kind; vector routines validate usable model/dimensions. Malformed/orphan embeddings remain canonical and are usually skipped or have no candidate. Recovery recognizes only a matching user embedding in the narrow interrupted-turn suffix. | Producer convention, not a mandatory reference invariant. |
| R17 | `retrieval_selection.content.{turn_id,selected[],provenance[].event_id}` | `RuntimeLoop` after hybrid retrieval; direct append subject to source policy | Runtime construction aligns selected IDs and provenance, but persisted references are not independently validated. CLI reads the selection. `AutonomyKernel._verify_recent_selections` recomputes a pure-vector ranking, checks intersection with its top five rather than reproducing hybrid retrieval, repeatedly scans trailing selections, and appends `reflection` as the result. | Runtime records auditable hybrid selections; the current verifier does not validly verify the full hybrid mechanism and can emit repeated misleading narrative reflections. |

### R18–R24: long-range memory, checkpoints, dormant context, and diagnostics

| ID | Surface | Every in-repository production producer found | Validation, preservation, consumers, and promotion | Strongest supported conclusion |
|---|---|---|---|---|
| R18 | `lifetime_memory.meta.sample_ids[]` | `build_lifetime_memory` | Builder samples real bounded messages. Retrieval integer-converts and existence-checks each ID before expansion. Kind, span membership, ordering, duplicates, and cardinality are not validated from stored data. | Builder-safe and retrieval-filtered, not a general span/evidence guarantee. |
| R19 | `lifetime_memory.meta.{cids[],concepts[]}` | `build_lifetime_memory` from current commitment/concept projections | Retrieval uses concepts for structural summary discovery and CIDs for MemeGraph thread expansion. Entity existence/state, attribution, and cardinality are unchecked; unknown handles expand to nothing. | Handles influence recall without entity-state or role validation. |
| R20 | `lifetime_memory.meta.{span_start,span_end,covered_until}` | `build_lifetime_memory` | The next builder run trusts prior `covered_until`. No dedicated schema checks range, continuity, gaps, or overlap. Malformed values may raise; plausible wrong values can silently alter future coverage. | Coverage cursor is trusted, not relationally verified. |
| R21 | `checkpoint_manifest.content.{up_to_id,root_hash,covers}` | CLI checkpoint command; autonomy checkpoint maintenance; direct append subject to source policy | Normal producers use a real summary and hash the prefix. Mirror/LedgerMirror fast rebuild and idempotence checks trust parsed boundary/root claims; malformed integers may raise and plausible wrong boundaries may skip replay. | Normal producer construction is stronger than replay-time enforcement. Checkpoint authority and boundary semantics remain unsettled. |
| R22 | Event `meta.context.{thread_id,parent_event_id}` | No managed producer found; public/programmatic event append | AutonomyKernel now registers ContextGraph as a required, completely rebuilt projection. The projection does not validate parent existence, order, cycles, or thread consistency. No production query caller for its accessors was found. | Required delivery but operationally dormant and relationally unvalidated. |
| R23 | Input-event `meta.relevant_concepts[]` | No managed runtime producer found; possible programmatic input-event caller | Retrieval accepts a list as concept seeds and canonicalizes/expands it. No canonical validation, attribution, token-definition, cardinality, or typed failure path exists. | An ungoverned programmatic retrieval-input surface. |
| R24 | `validation_failure.meta.about_event` | Managed evidence-designation and claim-validation failures; direct append | Managed producer links the just-created assistant by construction. No append validator checks positive ID, existence, kind, order, or uniqueness. Diagnostic readers consume the failure content; no production target dereferencer or graph promotion was found. | Reliable by managed producer convention only; not an append-wide relational guarantee. |

### R25–R28: canonical control-plane references

| ID | Surface | Every in-repository production producer found | Validation, preservation, consumers, and promotion | Strongest supported conclusion |
|---|---|---|---|---|
| R25 | `pmm_database_identity.database_uuid` and `WriterAuthority.database_uuid` | First governed `WriterSession` acquisition creates the singleton identity; later acquisitions load it | A shared writer session supplied to another `EventLog` must match the target database UUID or initialization fails. The identity governs writer-session attachment, not R15 inter-ledger identity. | Implemented and mandatory for audited shared writer sessions. Hostile control-table modification remains outside scope. |
| R26 | `pmm_writer_lease.{owner_id,fence,lease_expires_at,last_db_time}`; supporting PID/host/role | Writer acquisition, heartbeat, release, and expired-owner takeover | Every EventLog write reserves the database and validates current owner, fence, live lease, and clock. Connection functions plus a SQLite trigger reject unowned inserts on governed connections. Runtime checks authority before and after provider generation; stale results are discarded. | Implemented and mandatory for audited canonical writers. Raw hostile SQLite administration, trigger removal, or forged connection functions is outside scope. |
| R27 | Required projection registration `{name,required,applied_through}` and `pmm_projection_status.{owner_id,fence,applied_through,failed_event_id,state}` | RuntimeLoop registers required MemeGraph, Mirror, ConceptGraph; AutonomyKernel registers required Mirror, ContextGraph, ConceptGraph; EventLog records health | Rebuild-to-listener handoff and barriers replay every canonical event through a fixed watermark. Callback failure poisons writer health and produces typed barrier or post-commit errors. Persistent status is diagnostic and is not reloaded as projection authority. A callback’s internal silent no-op still advances the watermark. | Required delivery is implemented and mandatory on audited managed paths; semantic processing inside a successful callback is not guaranteed. |
| R28 | `events.prev_hash` and `events.hash` | Every EventLog append boundary, including terminal outcomes and commitment closes | Stage 3 selects the canonical predecessor inside the same `BEGIN IMMEDIATE` fenced transaction. The general append path deduplicates an identical hash; terminal outcomes and commitment closes converge through their own transactional state checks and unique indexes. Metrics, diagnostics, and exporters inspect continuity. Normal projection/retrieval reads do not first verify the complete historical chain. | Transactional non-forking production is implemented for audited writers. R28 existed before `ef63a8f` but was omitted from the prior inventory; historical tamper detection is diagnostic rather than a mandatory promotion gate. |

## Current coverage gaps

- R01 direct append can bypass the managed helper’s field shape while still being fenced as a write.
- R02, R03, and R04 allow omission where future policy may decide a reference is required.
- Direct canonical claims marked `validated:true` can enter R06 identity scanning.
- R07 and R09–R14 retain helper/schema bypasses through public append; fencing governs the writer, not the reference content.
- R16–R24 generally rely on producer construction or consumer filtering rather than mandatory append-time reference validation.
- R22 and R23 have no managed producer, so intended external/programmatic behavior remains unclosed.
- External provider metadata and external programmatic EventLog callers cannot be exhaustively enumerated from this repository.

## Current enforcement and relational-integrity gaps

- Existing targets are often not checked for allowed kind, role, ordering, same token/CID/version/thread, cardinality, or cycle safety.
- Identity adoption establishes a token and ordered chain but not subject, asserting actor, relationship predicate, object, or anchor relevance.
- Concept supersession, aliases, relations, and bindings can affect authoritative concept state or retrieval without uniform ledger-aware relationship checks.
- Duplicate R07 opens can overwrite the Mirror’s current CID entry.
- R15 does not bind foreign references to the available database UUID and does not revalidate target hash or role.
- R17 compares incompatible retrieval mechanisms and records the result as narrative reflection.
- R21 fast rebuild trusts stored boundary claims rather than independently establishing their complete relational validity.
- Required projection delivery cannot detect a projection callback that intentionally or silently treats malformed canonical content as a no-op.
- R28 history is not mandatorily verified before projection or retrieval.

## Silent degradation and rejection behavior

- Invalid managed evidence designations and parsed claims preserve the assistant utterance and append typed `validation_failure`; the invalid structure is not promoted.
- Malformed claim lines may never become extracted candidates or typed failures.
- Malformed or dangling reflection, concept, binding, embedding, lifetime-memory, and context references can remain canonical while their edge, binding, or retrieval expansion is omitted.
- Missing lifetime-memory samples and unknown CIDs or concepts silently contribute no expansion.
- Malformed model REF lines disappear; well-formed missing targets produce explicit unverified inter-ledger records.
- Required callback exceptions fail closed, but internal projection skips do not raise and therefore advance R27 watermarks.
- A canonical append followed by required projection failure remains preserved and is reported distinctly from an uncommitted append failure.

## Current integrity position

| Layer | Strongest supported conclusion |
|---|---|
| Historical preservation | Managed assistant utterances and canonical accepted events are retained; parsed validation rejection has a distinct failure form. Malformed unparsed structures may remain only in utterance history. |
| Writer governance | R25–R26 are implemented and mandatory for audited canonical writers. |
| Hash-chain production | R28 predecessor selection is transactional and fenced for audited writers; historical verification is not a mandatory read/promotion gate. |
| Projection delivery | R27 fixed-watermark delivery is implemented and mandatory for required managed projections; successful semantic handling inside callbacks is not guaranteed. |
| Referential validation | Strong on R08 and selected managed evidence paths; conditional, producer-conventional, or absent elsewhere. |
| Relational integrity | Partially enforced. R01 conversational promotion and R08 close transitions have narrow role checks; most other surfaces lack uniform permitted-role rules. |
| Semantic adequacy | Unresolved. No typed edge, selected ID, or validated structure proves that content warrants an interpretation. |

## Tests inspected as corroborating evidence

Relevant coverage includes:

- `test_terminal_outcomes.py`
- `test_evidence_designations.py`
- `test_claim_evidence_validation.py`
- `test_validation_failure_diagnostics.py`
- identity-manager and identity-claim tests
- commitment-manager, authoritative-close, Mirror, and MemeGraph tests
- concept schema, graph, binding-attribution, and retrieval tests
- inter-ledger reference and replay-narration tests
- vector, lifetime-memory, and checkpoint tests
- `test_runtime_memegraph_startup.py`
- `test_c02_prior_conversation.py`
- `test_stage3_writer_governance.py`

The local full suite passed `468` tests at the audit boundary. This corroborates exercised behavior; it does not prove that external callers or untested bypasses do not exist.

## Auditor finding

- **Repository state:** Clean synchronized `main` at `a615af55e9d8a4701a35f23d99c4f2f850229ca0`; prior inventory boundary `ef63a8f59e32b35594261e98e4befb5fa78f3dc2`.
- **Claimed guarantee:** This is a current as-is inventory of in-repository production-dereferenced reference and authority surfaces, not a claim of general reference integrity.
- **Actual mechanism:** Semantic extraction, manager helpers, EventLog special append boundaries, SQLite authority controls, rebuildable projections, retrieval, and consumer-side filtering provide uneven layers of enforcement.
- **Production paths:** R01–R28 above cover runtime, one-shot, MCP, autonomy, CLI, metrics, maintenance, experiments, public append, projection rebuild, retrieval, and diagnostic consumers found in the repository.
- **Validation paths:** Strong for R08, R25–R28, and managed R01 promotion; conditional or producer-conventional for most other surfaces.
- **Bypass or degradation paths:** Fenced public append bypasses most content schemas; projections can silently skip malformed canonical content; external providers and callers are not a closed set; hostile SQLite administration is outside scope.
- **Preserved form:** Assistant utterances, accepted canonical events, typed validation failures, malformed/dangling canonical history where append accepts it, and durable projection-health diagnostics.
- **Promoted form:** Terminal state, graph edges, prior conversational context, claims, identity adoption, commitment state, concept topology/bindings, retrieval candidates, lifetime-memory coverage, checkpoint boundaries, writer authority, and required projection state.
- **Integrity tier:** Mixed: strong governance and required delivery on audited managed paths; conditional referential integrity; partial relational integrity; unresolved semantic adequacy.
- **Coverage status:** Writer fencing and required managed projection delivery are mandatory across audited paths. Reference-specific validation is not mandatory across R01–R24.
- **Enforcement status:** R08 and R25–R28 enforce their stated narrow structural/governance invariants within scope. Most other surfaces omit one or more existence, kind, order, role, state, attribution, cardinality, cycle, or semantic predicates.
- **Strongest supported conclusion:** PMM governs who may append, which canonical predecessor is used, and whether required projections are current. It does not generally govern whether references inside canonical events are required, role-correct, relevant, or semantically warranted.
- **Implementation evidence:** R08 `adf3e57`; C01 `e2caabf`; C02 stages 1–2 `5570150`; Stage 3 `69cbe30`; later `9d446fc` and `a615af5` are documentation-only.
- **Relevant tests:** Current local full suite: `468 passed in 23.02s`; focused suites cover the principal managed and control-plane mechanisms.
- **Post-change verification:** Not applicable to runtime behavior; this replacement is documentation-only. Publication checks are reported separately when performed.
- **Proposed changes:** None in this inventory. Requirements, roles, rejection forms, and promotion policy belong in a separate explicitly authorized reference-policy matrix.

## Policy boundary and next sequence

This inventory answers:

> What exists, who produces it, who consumes it, and what is currently enforced?

It does not answer:

> What should be required, optional, forbidden, validated, rejected, preserved, projected, or promoted?

Those decisions belong in a separate policy-matrix artifact. The currently recommended development sequence is:

```text
publish refreshed R01–R28 inventory
  -> repair R17 retrieval verification as a separate bounded implementation
  -> create an explicit reference-policy matrix
  -> select one relational surface
  -> authorize one bounded enforcement patch
  -> leave semantic adequacy open
```

R06 is a plausible first relational candidate after the matrix because the current identity structure cannot distinguish user-directed or third-party assertions from self-directed identity adoption. R07 duplicate-open governance remains a separate mechanical policy task. Neither choice is authorized or implemented by this document.
