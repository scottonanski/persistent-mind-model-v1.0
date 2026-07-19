# Production Cross-Event and Cross-Entity Reference Inventory

Audit date: 2026-07-18
Repository revision: `ef63a8f59e32b35594261e98e4befb5fa78f3dc2` (`main`)
Audit method: PMM Development Auditor, current working tree

## Repository and evidence state

At the start of this inventory, `git status --short --untracked-files=all` was empty and `main` was neither ahead of nor behind its configured upstream. Three ignored local files were present: `chat_session_2026-07-18_21-26-12_ledger.json.gz`, `readable.md`, and `telemetry.md`. They are not repository evidence.

The inventory audit directly observed a clean tracked working tree and a prior local full-suite result of `427 passed in 16.72s`. The authorized R08 implementation later changed the working tree and most recently produced `431 passed in 16.05s`. These are local observations, not facts independently established by GitHub. The ignored 11-turn telemetry export is likewise only local observational evidence and is not a checked-in or reproducible baseline.

Four blind-test executions have been described historically, but no committed execution artifacts were found. The repository establishes the blind-case definitions and evaluation rubric; it does not establish that those four executions succeeded. This inventory therefore treats the executions only as historical claims.

## Scope, method, and limits

This inventory includes serialized fields and model-supplied structures that production code uses relationally to affect canonical events, deterministic projections, identity, commitments, concept state, graph relationships, fast reconstruction, or future retrieval. Production code was inspected first, followed by schema helpers, deterministic projections, tests, runtime evidence, and documentation.

Excluded are telemetry-only fields, temporary variables, tests as producers, archived or experiment-only formats without production consumers, and stored provenance that production never dereferences relationally. In particular, `claim_from_text.content.source_event_id`, `outcome_observation.content.evidence_event_ids` / `commitment_id`, and coherence-check comparison IDs are recorded but have no production relational consumer found in this revision. `reflection.meta.meta_summary.about_event` is also excluded: it is nested summary prose metadata, and no production dereferencer was found.

“Every producer” below means every in-repository production producer found by tracing event append sites, semantic-extraction entry points, projection rebuilds, and retrieval consumers. A public `EventLog.append` call remains an alternate programmatic producer for every accepted event kind; where it bypasses a helper, that is stated explicitly. Absence of another producer or consumer in these searches is not proof that an external caller does not exist.

Abbreviations used in the tables: **Y** yes; **N** no; **Opt** optional; **Req** required by that producer/path; **S/O** silent skip or omission; **AR** authorization required. “Current-turn” means membership in the events selected for the current model turn, not merely existence in the ledger.

## Reference-surface table

### A. Surface, producers, and parsing

| ID | Event kind / serialized field or structure | Every in-repository production producer found | Parser, schema, or extraction path |
|---|---|---|---|
| R01 | Protocol terminal outcome: `assistant_message` or `generation_failure`, `meta.about_event` | `RuntimeLoop` managed-turn success/failure and interrupted-turn recovery call `EventLog.append_terminal_outcome`; direct `EventLog.append` can write legacy forms | `EventLog.append_terminal_outcome`; SQLite partial unique index for protocol v1; runtime recovery reads protocol and `about_event` |
| R02 | `reflection.meta.about_event` | `RuntimeLoop` delta reflection; callers may append through `EventLog`; deterministic user-turn and autonomy reflections usually omit it | `MemeGraph._process_event` reads integer-like value only when the target already has a tracked meme node |
| R03 | Assistant JSON header `evidence_designations[] = {event_id, supports}` | Model output through `RuntimeLoop`; no other producer found | `SemanticExtractor.extract_assistant_json_header`; `validate_evidence_designations`; validated value copied into assistant metadata |
| R04 | Claim `data.evidence_events[]` | Model `CLAIM:` lines through `RuntimeLoop`; direct callers of claim validator are possible, but canonical claim production found only in the loop | `SemanticExtractor.extract_claims`; `_validate_evidence_references`; `validate_claim_detailed` |
| R05 | Claim `event_existence.data.id` and `reference.data.id` | Model `CLAIM:` lines through `RuntimeLoop` | Claim JSON extraction; `validate_claim_detailed`; `reference` also loads the target to inspect kind |
| R06 | Identity claim token chain and `identity_adoption.meta.{proposal_event_id,anchor_event_id,anchor_kind,ratify_event_id}` | Model identity proposal/ratification claims; `IdentityManager.process` produces adoption; any direct validated claim append can enter its scan | Claim validator plus full-ledger `IdentityManager` scan; adoption metadata is emitted by manager, not independently schema-validated |
| R07 | `commitment_open.meta.cid` | `CommitmentManager.open_commitment`; `open_internal_goal`; direct `EventLog.append` callers | `SemanticExtractor.extract_commitments`; `CommitmentManager`; optional standalone `validate_event` schema is called by manager paths, not by `EventLog.append`; `Mirror` reads `cid` |
| R08 | `commitment_close.meta.{cid,source,open_event_id}` | Runtime model closures use `CommitmentManager.apply_closures`; autonomy stale-goal, gap-resolution, and internal-goal paths use manager closure methods; generic `EventLog.append` delegates close writes to the same atomic boundary | `SemanticExtractor.extract_closures`; `EventLog.append_commitment_close` resolves the latest lifecycle event under a write transaction; `Mirror`, `MemeGraph`, lifetime-memory builder, and evaluators consume the close |
| R09 | `config` structure `{type:"exec_bind", cid, exec, params}` | Runtime commitment-opening path for idle-monitor commitments; direct config append callers | Runtime JSON construction; router/config scan checks basic shape; `EventLog.has_exec_bind` compares `cid` |
| R10 | `concept_define.meta.supersedes`, concept token/version/concept ID history | `seed_ctl_ontology`; `ConceptOpsCompiler` from assistant `concept_ops`; direct append callers | Concept payload helper; standalone schema validator exists but append/compiler do not invoke it; `ConceptGraph` JSON/meta projection |
| R11 | `concept_alias.content.{from,to}` | `ConceptOpsCompiler`; direct append callers | Concept payload helper; compiler canonicalizes and checks `from != to`; standalone validator is not invoked by append; `ConceptGraph` projects alias map |
| R12 | `concept_relate.content.{from,to,relation}` | `ConceptOpsCompiler`; `seed_ctl_ontology`; direct append callers | Concept payload helper; compiler canonicalizes/deduplicates exact tuple; standalone validator is not invoked by append; `ConceptGraph` projects edge |
| R13 | `concept_bind_event` / `concept_bind_async` `{event_id,tokens,relation}` and attribution metadata | Runtime user/assistant indexing; runtime claim projection; `ConceptOpsCompiler`; `Indexer`; autonomy concept maintenance; binding-audit maintenance tool; direct append callers | Binding payload helper or hand-built JSON; `EventLog.append` conditionally validates attribution metadata; `ConceptGraph` parses both kinds |
| R14 | `concept_bind_thread` `{cid,tokens,relation}` and attribution metadata | Runtime after commitment open; `Indexer.backfill_concept_thread_bindings`; direct append callers | Hand-built/helper JSON; `EventLog.append` validates attribution metadata only; `ConceptGraph` projects token-to-CID membership |
| R15 | `inter_ledger_ref` target encoded as `REF:<path>#<id>` plus `meta.target_hash` / `verified` | Model assistant full-JSON `refs` or `REF:` lines processed by `RuntimeLoop`; no conversion of autonomy reflection `refs` was found | `_parse_ref_lines` string parsing; opens target SQLite ledger, loads ID, captures hash; failed lookup still produces an unverified record |
| R16 | `embedding_add.content.event_id` | Runtime `ensure_embedding`; `Indexer`; autonomy maintenance; CLI/backfill path; direct append callers | JSON vector loader and embedding scans; no event-reference schema at append |
| R17 | `retrieval_selection.content.turn_id`, `selected[]`, `provenance[].event_id` | `RuntimeLoop` after vector retrieval; direct append callers subject to source policy | Runtime JSON construction; CLI readers; autonomy retrieval verification parser |
| R18 | `lifetime_memory.meta.sample_ids[]` | `build_lifetime_memory` | Direct metadata construction from sampled ledger messages; retrieval pipeline converts IDs and calls `eventlog.exists` |
| R19 | `lifetime_memory.meta.{cids[],concepts[]}` | `build_lifetime_memory` | Derived from commitment/concept projections; retrieval uses CIDs for meme-thread expansion and concepts for structural summary recall |
| R20 | `lifetime_memory.meta.{span_start,span_end,covered_until}` | `build_lifetime_memory` | Builder reads the last chunk’s `covered_until` to choose its next start; values are integer-converted without a dedicated schema |
| R21 | `checkpoint_manifest.content.up_to_id` | CLI checkpoint command; autonomy checkpoint maintenance; direct append callers subject to source policy | JSON parser in `LedgerMirror.rebuild_fast`; producers hash the prefix through the latest summary |
| R22 | Event `meta.context.{thread_id,parent_event_id}` | No in-repository production producer was found; accepted through public event append and consumed by production `ContextGraph` rebuild/listener | `ContextGraph._process_event` reads the metadata directly; tests demonstrate direct append only |
| R23 | Input-event `meta.relevant_concepts[]` | No producer in the managed runtime was found; possible programmatic user-event callers | Retrieval pipeline reads the list directly and seeds concept canonicalization/expansion |
| R24 | `validation_failure.meta.about_event` | `RuntimeLoop` evidence-designation and claim-validation failure paths; direct append callers | Loop writes the just-created assistant event ID; one-shot diagnostics parse failure content but do not dereference `about_event` |

### B. Validation coverage and invocation conditions

| ID | Omit? | Empty accepted? | Target existence | Current-turn availability | Kind/type | Ordering | Other relational checks | Validator invocation and failure behavior |
|---|---|---|---|---|---|---|---|---|
| R01 | Protocol path N; legacy Opt | N/A | N | N | Outcome kind constrained; target kind N | N | Positive integer and one protocol-v1 terminal per `about_event` | Helper always checks shape; DB enforces uniqueness. Bad shape raises before append; duplicate raises. Legacy direct append bypasses protocol uniqueness. |
| R02 | Y | `None` acts omitted | N | N | N | N | Target must already be a tracked meme node for an edge | No validator. Bad/missing/unrepresented target leaves reflection canonical and omits the edge. |
| R03 | Y | Y | Indirect: selected IDs came from ledger retrieval | Y | N | N | Positive int, nonempty `supports`, no duplicate `(event_id,supports)` | Invoked only when header contains the key. Any bad member rejects the whole designation collection, omits it from assistant metadata, and appends `validation_failure`. |
| R04 | Y | Y | Y | Y in managed runtime | N | N | Positive integer elements; duplicates accepted | Invoked for each parsed claim; selected-ID check only when caller supplies selection IDs (runtime does). Invalid claim is not promoted; `validation_failure` is appended. |
| R05 | Claim type determines | N/A | Y | `event_existence`: N; `reference`: Y in runtime | `reference` requires target `claim`; `event_existence` any kind | N | None | Invoked for parsed claims. Missing target/type/current-selection rejects claim. Unguarded `int(data.id)` can raise for malformed values rather than return a typed validation result. |
| R06 | Adoption IDs Req | Token cannot be empty on validated proposal/ratify | Events are found in the manager’s scan | N | Proposal/ratify claim kinds and anchor kind checked | proposal < anchor < ratify | Same token; one adoption per token. Anchor relevance/role is not checked | Claim validator runs in loop; manager later scans all `claim` events marked validated. No adoption event if chain absent. Direct forged `validated:true` claim metadata is trusted. |
| R07 | Manager N; append can omit | Manager N | N/A (CID names entity) | N | Origin schema when manager calls it | N | Internal prefix/origin/goal shape; duplicate CID N | Manager validates; append does not. Mirror accepts any truthy `cid`; duplicate open overwrites canonical open-map entry. |
| R08 | N | N | Y: latest CID lifecycle event must be `commitment_open` | N | Latest target kind must be `commitment_open` | Y, by latest lifecycle event | Nonempty CID/source; exact `open_event_id`; unique close per open event; repeat close is idempotent | Always invoked for new close writes, including generic append. Manager unknown CID returns no event; generic append raises; repeat close returns the existing ID and creates no event. |
| R09 | `cid` expected by producer | Empty string can pass some reader shape checks | N | N | `exec`/params shape only | N | Does not require an open commitment | No dedicated relational validator. Malformed entries are skipped by router; an orphan bind can be canonical and can affect dedup/executor discovery. |
| R10 | `supersedes` Y | Falsey omitted | N | N | String only in standalone validator | N | No same-token, prior-version, cycle, or version-monotonicity check | Helper checks basic definition shape; append/compiler skip standalone validator. Projection accepts truthy supersedes; malformed event is silently skipped. |
| R11 | N in helper | Helper N | N | N | Token strings in helper | N | `from != to` on compiler path; no target definition or cycle check | Helper/compiler failures raise before append. Direct malformed append remains history and projection skips it; alias cycles fail only when canonicalization encounters them. |
| R12 | N in helper | Helper N | N | N | Strings in helper | N | Exact-tuple dedup on compiler path; no endpoint, relation registry, role, cardinality, or cycle checks | Helper/compiler shape failure raises. Direct malformed append remains history and projection skips it. Undefined endpoints are projected. |
| R13 | Shape path N | Empty token list rejected by helper but direct append accepted and projects nothing | Compiler target Y; other producers use known event; append/projection N | N | `model_declared.origin_event_id` must be assistant; bound target kind N | N | Attribution v1 shape; other origins’ origin IDs and `derived_from_binding_event_id` get positive-int checks only | Attribution validator runs on every bind append but permits legacy metadata. Only model-declared origin is dereferenced. Bad content generally survives append and is silently skipped/partially projected. |
| R14 | Shape path N | Empty token list possible via direct append | CID existence/open state N | N | N | N | Attribution shape only; no CID/token/relation/cardinality rules | Same attribution invocation as R13. Bad JSON/shape can remain canonical and project nothing; orphan CID bindings are retained in concept projection. |
| R15 | Model refs Y | Empty refs accepted as no action | Checked in foreign ledger at creation only | N | Target kind N | N | Path/ledger identity/role N; hash captured but not revalidated later | Malformed refs are silently ignored. Missing target produces canonical `verified:false`; found target produces `verified:true`. |
| R16 | N in producers | N/A | N at append/load | N | Target kind N | N | Vector dimensions/model checked by vector routines, not target relation | Producer paths use real events. Malformed vector records are skipped; orphan embeddings can remain canonical and normally have no retrievable candidate. |
| R17 | Runtime emits required fields | Empty selection Y | Producer uses current candidates; stored record not revalidated | It records current turn but later readers do not verify membership | N | `turn_id` is used as a cutoff, not validated as assistant kind | Selected/provenance alignment only by producer construction | No event-reference validator. Parse failures are skipped; malformed numeric fields can abort a reader path. Source policy may reject the entire append with a `violation`. |
| R18 | Builder emits list | Y | Retrieval checks Y per sample | N | Sample kind N | Span membership/order N | Duplicate/cardinality enforcement only by builder sampling behavior | No append validator. Bad IDs are skipped; nonexistent IDs are omitted from expanded retrieval. |
| R19 | Builder emits lists | Y | CID/concept existence N | N | N | N | No attribution, open-state, or cardinality check | No validator. Unknown CIDs yield empty thread slices; undefined concepts may still canonicalize and participate as keys. |
| R20 | Builder emits | N/A | Boundary IDs come from ledger in producer; stored value not checked | N | N | Monotonicity only assumed | No range, overlap, or continuity validation | Bad `covered_until` can raise during a later build; plausible but incorrect boundaries silently change what future chunks cover. |
| R21 | Producer N | N/A | Prefix is read without confirming referenced event exists/is summary | N | N | N | Root hash and `covers` are not validated during fast rebuild | Producers construct from a real summary; append accepts direct values. Fast rebuild trusts parsed `up_to_id`; malformed integer can raise, plausible bad boundary can skip replay silently. |
| R22 | Y | Empty thread is ignored | N | N | N | N | No parent/thread consistency, cycle, or cardinality checks | No validator. Bad/missing context is ignored; nonempty values create projection nodes/edges even for nonexistent parents. |
| R23 | Y | Y | Concept definition existence N | Current input only | List check only | N | No token/alias/attribution/cardinality rules | Retrieval consumes only a list; arbitrary elements reach canonicalization. No canonical event or typed failure is created for bad metadata. |
| R24 | Managed producer N; append Opt | N/A | Producer knows target exists; append N | Target is current assistant in managed path | Target kind N | Producer orders failure after assistant; append N | Positive integer not enforced by append; no uniqueness/cardinality rule | No dedicated validator. Managed path is structurally reliable by construction; malformed direct append remains canonical. |

### C. Preservation, promotion, consumers, and effects

| ID | Historical form preserved after failure | Silent degradation / omitted projection | Canonical event or state that may be created | Every downstream production consumer found | Graph, projection, identity, commitment, concept, or retrieval effect |
|---|---|---|---|---|---|
| R01 | Earlier user and any prior suffix remain; rejected terminal is absent | Duplicate/invalid write is loud; recovery can silently decline to synthesize when suffix is not exactly recoverable | Terminal outcome linked to a user turn | Managed-turn recovery, terminal-outcome lookup/uniqueness | Determines whether a user turn is terminal and whether recovery appends failure |
| R02 | Reflection event remains | Y, edge omitted | Reflection canonical event; optional `reflects_on` meme edge | `MemeGraph`; identity manager also treats reflection kind as an anchor independent of link | Graph relation only; reflection content still affects RSM/context, and any reflection can anchor identity |
| R03 | Full assistant utterance remains; invalid structure is not copied | Designation projection omitted, with typed failure | Assistant plus optional validation failure | No downstream relational consumer was found after `RuntimeLoop` stores the validated metadata; claim evidence is validated separately | Changes the canonical assistant metadata only; does not itself authorize claim promotion |
| R04 | Full assistant utterance remains | Claim omitted, with typed failure | Validated claim and its concept binding, or validation failure | Identity manager, RSM, claim/context readers, concept graph via generated binding | Can create canonical claims, identity inputs, and retrieval-visible concept bindings |
| R05 | Full assistant utterance remains | Claim omitted with typed failure, except malformed conversion may interrupt post-response processing | Same as R04 | Same as R04 | Same as R04; `reference` specifically requires a selected claim target |
| R06 | Proposal/anchor/ratify events remain even if no adoption | No adoption when chain fails; irrelevant anchor can nonetheless promote | `identity_adoption` and identity concept/meme records | Identity views/summary, `ConceptGraph`, `MemeGraph`, RSM | Changes authoritative adopted-identity projection and future identity context |
| R07 | Open event always remains once appended | Missing/invalid CID may be ignored by Mirror; duplicate silently replaces open-map value | Open commitment state and graph node | `Mirror`, `MemeGraph`, context/lifetime memory, evaluators, runtime close logic | Establishes open commitment keyed by CID and commitment thread |
| R08 | Legacy close history remains replayable; a rejected new attempt creates no close event | N for new writes; legacy records retain CID fallback projection | One authoritative close linked to the exact open event | Same commitment consumers as R07; `MemeGraph` prefers `open_event_id` and falls back to CID only for legacy history | Atomically removes the current open CID on replay and creates an exact `closes` graph edge for new records |
| R09 | Config event remains | Malformed/orphan bind may be skipped by router; matching CID can still suppress later behavior | Executor binding configuration | Router/config loader, `EventLog.has_exec_bind`, autonomy close suppression | Associates execution behavior with CID and affects whether internal goals auto-close |
| R10 | Concept definition event remains | Malformed projection skipped; invalid supersession may still project | Current definition/history/supersession relation | `ConceptGraph`, context/retrieval concept APIs | Replaces current token definition and records version lineage used in concept state |
| R11 | Alias event remains | Malformed skipped; unresolved/cyclic alias errors emerge later | Alias mapping | `ConceptGraph` canonicalization used by retrieval, bindings, context, compiler | Redirects concept identity globally |
| R12 | Relation event remains | Malformed skipped; otherwise even undefined endpoints project | Concept edge | Concept graph/context/topology/metrics and retrieval neighborhood paths | Changes deterministic concept topology |
| R13 | Binding event remains | Y: malformed/empty structures may project partially or not at all | Event-to-concept bindings and attribution record | `ConceptGraph`, retrieval expansion/scoring/context, Indexer propagation | Makes events retrievable by concept; tokens need not be defined |
| R14 | Thread-binding event remains | Orphan CID projects but later meme expansion may be empty | Concept-to-CID thread membership | `ConceptGraph` and retrieval pipeline with `MemeGraph` | Lets concept retrieval pull commitment thread slices |
| R15 | Original assistant remains; canonical unverified ref may also remain | Malformed lines disappear; failed target is explicit rather than omitted | Verified or unverified inter-ledger reference | Runtime dedup/failed-ref scans, autonomy candidate logic, replay narrator | Records external provenance and affects whether a target is retried/suggested; no later foreign dereference found |
| R16 | Embedding event remains | Y: unusable/orphan vectors are skipped or have no candidate | Vector index entry keyed by event ID | Vector loader/search, recovery suffix check | Enables similarity retrieval; matching user embedding participates in interrupted-turn recovery |
| R17 | Selection event remains | Parse failures skipped; bad references can distort/abort verification | Retrieval audit record; later autonomous verification reflection may be emitted | CLI retrieval audit/verify, autonomy verifier | Historical selection can influence later verification/reflection, not canonical selected memory itself |
| R18 | Lifetime-memory event remains | Y: bad/missing samples omitted from expansion | Summary chunk plus evidence-tail handles | Retrieval summary vector and pinned-summary expansion | Pulls referenced event samples into future context |
| R19 | Lifetime-memory event remains | Y: unknown handles expand to nothing | Summary concept/CID index | Retrieval structural-summary and commitment-thread expansion | Makes summaries discoverable by concept and capable of recalling commitment slices |
| R20 | Lifetime-memory event remains | Plausible wrong boundary silently omits or duplicates future summarized spans | Coverage cursor for later lifetime-memory events | Lifetime-memory builder | Determines which historical span is summarized next |
| R21 | Manifest remains | Plausible wrong boundary can silently omit replay; malformed may fail loudly | Trusted fast-rebuild boundary | `Mirror.rebuild_fast`, `LedgerMirror.rebuild_fast`, and checkpoint idempotence checks | Determines authoritative RSM replay start during fast reconstruction |
| R22 | Original event remains | Y: context omitted on bad shape; dangling parents can remain in projection | Context thread/parent projection only | `ContextGraph` rebuild/listener; no production query caller found | Currently dormant projection surface; no proven canonical/retrieval effect in this revision |
| R23 | Input event remains | Bad tokens may be ignored downstream or raise during canonicalization; no typed record | In-memory seed set only | Retrieval pipeline and `ConceptGraph.canonical_token` | Directly influences concept and event candidates for that retrieval |
| R24 | Assistant and failure event remain | The relation is not used to build a graph; diagnostics still report the failure from its own event/content | Typed canonical validation-failure history | One-shot diagnostics and event readers; no production target dereferencer found | Preserves which assistant the producer intended to diagnose, but currently has no authoritative projection effect |

### D. Tests, supported conclusions, and authorization boundaries

Tests are evidence only for their exercised paths; they are not treated as exhaustive proof.

| ID | Relevant tests | Strongest currently supported conclusion | Unresolved policy questions — AR |
|---|---|---|---|
| R01 | `test_terminal_outcomes.py` | Managed runtime writes are shape-checked and unique; generic/legacy target integrity is not guaranteed. | Must target exist, be current user kind, and precede outcome? Should legacy writes be forbidden? |
| R02 | `test_meme_graph.py`, reflection tests | `about_event` is optional and best-effort for meme edges; no referential-integrity guarantee exists. | Reflection-reference requirement, allowed target kinds/roles, ordering, and failure semantics. |
| R03 | `test_evidence_designations.py` | Valid designations are current-selection constrained; omission and empty list are accepted; invalid input preserves assistant plus typed failure. | Required/optional status and meaning of empty designations. |
| R04 | `test_claim_evidence_validation.py`, `test_evidence_designations.py`, `test_validation_failure_diagnostics.py` | Claim evidence is existence- and current-selection-checked in managed runtime, but target role/kind and duplicate/cardinality semantics are unspecified. | Required/optional/empty policy; allowed kinds, roles, attribution, and cardinality. |
| R05 | `test_validators.py`, `test_validation_failure_diagnostics.py` | Existence is checked; `reference` additionally requires a selected claim. Input normalization is not total. | Allowed claim-reference roles/kinds and whether malformed scalar IDs reject, quarantine, or abort. |
| R06 | `test_identity_claim_validation.py`, identity-manager tests | Token/order/anchor-kind mechanics exist; anchor relevance is not enforced, and validated metadata is a trust boundary. | Identity-anchor relevance, permitted anchors, and authority of direct canonical claims. |
| R07 | `test_commitment_manager.py`, `test_schemas.py`, `test_mirror.py` | Manager-produced opens have shape validation; append and projection do not guarantee global CID integrity. | CID uniqueness, collision behavior, origin requirements, and duplicate-open semantics. |
| R08 | `test_authoritative_commitment_close.py`, `test_commitment_manager.py`, `test_idempotent_closure.py`, `test_mirror.py`, `test_meme_graph.py`, autonomy reflection tests | Authoritative close semantics are implemented and mandatory for all in-repository producers and generic append: open-state resolution, idempotence, source retention, and exact open-event linkage are enforced atomically. | Retry policy remains explicitly outside this patch; duplicate-open governance is a separate R07 question. |
| R09 | `test_exec_binding_idle_monitor.py` | Exec-bind CID is operationally consumed without commitment existence/open-state validation. | Whether orphan/stale binds are allowed and which executor roles may bind which commitments. |
| R10 | `test_concept_schemas.py`, `test_concept_graph.py` | Supersession is recorded, not governed: existence, same-token lineage, order, and version monotonicity are not guaranteed. | Supersession and version-governance policy. |
| R11 | `test_concept_graph.py`, `test_concept_schemas.py`, `test_eventlog_ctl.py` | Compiler/helper enforce basic shape, while target existence and cycle prevention are not guaranteed at append. | Alias endpoint, cycle, identity, and migration policy. |
| R12 | `test_concept_graph.py`, `test_concept_ontology.py`, `test_concept_schemas.py` | Relations can connect undefined tokens; relation roles/cardinality are not governed. | Permitted target kinds, relation registry/roles, cardinality, and cycles. |
| R13 | `test_concept_graph.py`, `test_concept_graph_async.py`, binding-attribution tests, vector/retrieval tests | Bindings can alter retrieval without target-existence, token-definition, relation-role, or uniform attribution checks. | Direct/provisional/quarantined concept authorship; target kinds; token/relation/attribution rules. |
| R14 | Loop commitment tests, concept-thread/backfill tests | Thread bindings may reference non-open/nonexistent CIDs and still enter concept projection. | CID state requirements, token roles, cardinality, and stale-thread semantics. |
| R15 | `test_inter_ledger_ref.py`, `test_assistant_json_meta_and_ref_dedup.py`, `test_replay_narration.py` | Creation-time existence/hash can be observed, but ledger identity, target role, and later integrity are not guaranteed. | Permitted ledgers/paths/kinds, trust/attribution, revalidation, and retry policy. |
| R16 | `test_vector_backfill.py`, `test_retrieval_vector_phase1.py`, `test_terminal_outcomes.py` | Normal producers bind vectors to real events; append/load does not establish this as a mandatory invariant. | Orphan-vector handling, target kinds, replacement/version policy. |
| R17 | `test_retrieval_vector_phase1.py`, `test_policy_enforcement.py` | Runtime records internally consistent selections, but persisted references are not independently validated and can affect later autonomous reflection. | Retention/authority of selection records, target kinds, ordering, and malformed-record behavior. |
| R18 | `test_lifetime_memory.py` | Builder emits real bounded samples and retrieval existence-checks them; span/kind/order integrity is not guaranteed. | Allowed sample kinds, span membership, ordering, duplicates, and cardinality. |
| R19 | `test_lifetime_memory.py`, retrieval tests | Concept/CID handles influence future recall without entity-state validation. | Direct/provisional concept authorship and whether CIDs must exist/remain open. |
| R20 | `test_lifetime_memory.py` | Coverage cursor is trusted across chunks; continuity is not validated. | Overlap/gap policy, correction/supersession, and retry policy. |
| R21 | `test_checkpoint_manifest.py`, `test_policy_enforcement.py`, `test_cli_large_ledger_guardrail.py` | Normal producers anchor to a summary and hash the prefix; fast rebuild trusts `up_to_id` without verifying the manifest’s relational claims. | Checkpoint authority, boundary kind, root validation, failure/fallback, and supersession policy. |
| R22 | `test_context_graph.py`, `test_autonomy_integration_phase1.py` | Production projection accepts thread/parent metadata, but no managed producer or production query consumer was found. | Whether this surface is supported, forbidden, or dormant; parent existence/order/cycle/thread rules. |
| R23 | No focused producer test found | Retrieval honors caller-supplied concept seeds, but the managed runtime does not produce them and no integrity contract was found. | Who may supply seeds, permitted tokens, attribution, empty semantics, and malformed behavior. |
| R24 | `test_validation_failure_diagnostics.py`, `test_evidence_designations.py` | Managed paths link failures to the current assistant by construction; no append-time or consumer-time referential guarantee exists. | Whether diagnostic references require target existence/kind/order and how malformed links should be preserved. |

## Auditor finding

- **Repository state:** `main` at `ef63a8f59e32b35594261e98e4befb5fa78f3dc2`; tracked tree clean before this new document.
- **Claimed guarantee:** this is an as-is inventory, not a claim that all references have mandatory integrity enforcement.
- **Actual mechanism:** reference integrity is distributed among semantic extractors, manager-specific checks, optional schema helpers, `EventLog` special cases, deterministic projections, and retrieval-time best-effort filtering.
- **Production paths:** R01–R24 above identify the in-repository append, extraction, rebuild, and retrieval paths found.
- **Validation paths:** validation is strongest for current-turn claim evidence and manager-produced commitment operations; many CTL, projection, checkpoint, and retrieval references are validated only by producer convention or not at all.
- **Bypass/degradation:** public append paths bypass most schema helpers; malformed or dangling records often remain canonical while a projection or retrieval expansion is silently skipped.
- **Preserved form:** model failures usually preserve the assistant utterance; event-level failures frequently preserve the malformed/dangling canonical event itself.
- **Promoted form:** validated claims, identity adoptions, commitment map transitions, concept graph state, fast-rebuild boundaries, and retrieval candidate expansions are the principal promoted forms.
- **Integrity tier:** mixed—mandatory for a few managed paths, bypassable for many append paths, and best-effort for several projections.
- **Coverage status:** R08 is mandatory across all in-repository and generic append producers. The wider R01–R24 inventory remains partial by design because external callers, dormant surfaces, and dynamically supplied provider metadata prevent an absolute completeness claim.
- **Enforcement status:** R08 enforces CID existence/open state, source retention, exact open-event linkage, and idempotence. Enforcement remains nonuniform across the other inventory rows.
- **Strongest conclusion:** the repository supports a concrete inventory of the above production-dereferenced reference surfaces, but it does not support a general guarantee of cross-event or cross-entity referential integrity.
- **Implementation evidence:** the subsequently authorized R08 cycle added the atomic EventLog transition, routed manager/autonomy producers through it, added exact graph projection, and added focused lifecycle/concurrency tests. No other inventory policy was implemented.
- **Relevant tests:** listed per row and treated only as evidence for exercised paths.
- **Post-change verification:** R08 focused tests passed, the full suite passed (`431 passed in 16.05s`), all R08-changed Python files passed Ruff, R08 edits were checked with Black (`--target-version py39`) while unrelated baseline formatting was left untouched, production append searches found no weaker close producer, and `git diff --check` passed.
- **Proposed changes:** none beyond the authorized R08 implementation now reflected here.

## Discovered gaps

Coverage gaps:

- R22 and R23 have production consumers but no managed production producer found; external/programmatic production use cannot be ruled out.
- Provider-supplied `GenerationResult.meta` can flow into assistant metadata, including `concept_ops`; the set of external provider producers cannot be completely enumerated from this repository.
- Public `EventLog.append` is an alternate producer for accepted kinds, so helper-only guarantees are not repository-wide guarantees.

Enforcement and relational-integrity gaps:

- CTL schema validators are not generally invoked by `EventLog.append`, and several compiler/projection paths validate shape but not target existence, kind, role, order, version, attribution, or cardinality.
- Identity adoption checks token and event order but not whether the anchor is relevant to the proposed identity.
- Checkpoint and lifetime-memory coverage boundaries are trusted on replay or subsequent generation rather than relationally verified.
- Binding attribution validates `model_declared` origins more strongly than other origins; bound targets themselves are not uniformly checked.

Silent-degradation gaps:

- Meme and concept projections commonly retain canonical history while omitting an edge or binding.
- Missing lifetime-memory samples and unknown CIDs silently contribute no retrieval expansion.
- Malformed model reference lines can disappear without a typed failure; a well-formed missing inter-ledger target is, by contrast, preserved explicitly as unverified.

## Policy questions requiring authorization

No answer is selected here. Authorization is required for:

- whether each reference is required, optional, or forbidden, and what empty collections mean;
- unknown claim-type rejection or promotion;
- allowed target kinds, relational roles, token/CID/thread/version/attribution/cardinality constraints, and ordering rules;
- identity-anchor relevance;
- reflection-reference policy;
- supersession and version governance;
- direct, provisional, or quarantined concept authorship;
- semantic adequacy or model adjudication;
- retry, revalidation, quarantine, and historical-correction behavior;
- whether dormant R22/R23 inputs are supported public surfaces or should be rejected.

## Completed bounded candidate

**R08 — `commitment_close.meta.{cid,source,open_event_id}`** completed its authorized bounded implementation cycle. New canonical closes now represent successful state transitions, not attempted commands.

Automatic retry remains outside the implementation. Duplicate-open governance remains an R07 policy question and was not settled by closing the currently authoritative open event.

## Incompletely traced surfaces

- R22 (`meta.context`) and R23 (`meta.relevant_concepts`) could not be traced to a managed production producer.
- External `GenerationProvider` implementations and programmatic `EventLog` callers are outside the closed world of this repository; their possible metadata/reference production is not enumerable here.
- Inter-ledger targets are arbitrary local SQLite paths supplied in model text. Their downstream evolution and integrity cannot be traced from the source repository.
- No production consumer was found for several recorded provenance IDs listed in the exclusions. That finding is evidence of the searches performed, not proof that no dynamically loaded or future consumer exists.
