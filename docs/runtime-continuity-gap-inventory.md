# Runtime Continuity Gap Inventory

This document inventories two current continuity gaps without selecting policy or proposing an implementation:

1. normal persisted-ledger startup does not rebuild existing `MemeGraph` history;
2. recent conversation messages are read but are not automatically rendered into model context.

The inventory is grounded in production code at local `main` commit `28d09c9e623c00f8ee9da3f3c34fe29857858834` (`Align README claims with current PMM behavior`). A fresh fetch during the continuation audit confirmed that local `main` was one commit ahead of `origin/main` at `4ca84d6bcb25e106a620f77c9d29ef68eadc2d44`. The tracked working tree was clean, and this inventory was the sole untracked item.

## Evidence boundaries

- **Repository evidence** means current production code, schemas and projections, followed by tests that exercise named paths.
- **Direct local observations** are fresh disposable on-disk runs performed during this audit. Their databases were created under unique `/tmp` directories and deleted after inspection.
- **Historical claims** were not needed to establish either gap.

The passing tests cited below establish only their exercised paths. They do not establish normal persisted-startup parity or mandatory conversational-tail inclusion.

## Scope and exclusions

Included:

- interactive CLI, one-shot CLI, and MCP construction of `RuntimeLoop` over an existing SQLite ledger;
- `MemeGraph` construction, incremental observation, explicit rebuild paths, and production consumers;
- cross-restart commitment, reflection, identity, thread, retrieval, rendering, and lifetime-memory effects;
- production handling of the recent ledger tail, retrieval selection, context rendering, prompt composition, and provider input;
- existing tests and fresh persisted-runtime observations;
- policy choices that must be authorized before implementation.

Excluded:

- runtime, test, schema, validator, projection, retrieval, or prompt changes;
- choosing a graph persistence, checkpoint, cache, prompt-window, token-budget, or evidence-availability policy;
- R07 duplicate-open governance;
- semantic adjudication of whether a prior message or graph edge is relevant;
- retry policy.

## Summary

| ID | Narrow claim tested | Current result | Preserved state | Operational degradation |
|---|---|---|---|---|
| C01 | Opening an existing ledger through normal `RuntimeLoop` startup restores the same shared `MemeGraph` available before shutdown. | False. The shared graph starts empty and observes only later tracked events. | All ledger events remain; `Mirror` and `ConceptGraph` rebuild existing state; explicit `MemeGraph.rebuild` remains available. | Thread slices, graph neighbors, graph rendering, graph-derived retrieval reasons, lifetime-memory CID discovery, and cross-boundary edges can be missing. |
| C02 | The immediately preceding managed conversation is automatically included in the next model call. | False. `RuntimeLoop` reads a tail, but its contents are not rendered or merged into retrieval. | User and assistant events remain in the ledger and exports; they may still be selected by an independent concept, thread, lifetime-memory, or vector-refinement path. | A model can receive an explicitly empty evidence window despite the immediately preceding exchange being in `read_tail(10)`. |

Neither gap deletes history. Both weaken what the live runtime can reconstruct or show to a later model call.

---

## C01 — `MemeGraph` history is not rebuilt during normal persisted-ledger startup

### Narrow guarantee under audit

> Before the first retrieval on an existing ledger, every production `RuntimeLoop` has reconstructed the ledger's tracked `MemeGraph` nodes and edges.

The repository does not establish this guarantee.

### Production and startup path

`MemeGraph` tracks these event kinds:

- `user_message`;
- `assistant_message`;
- `commitment_open`;
- `commitment_close`;
- `identity_adoption`;
- `reflection`;
- `summary_update`.

`MemeGraph.__init__` creates an empty NetworkX graph. It does not read the ledger. `MemeGraph.rebuild(events)` is the explicit full-history path, while `MemeGraph.add_event(event)` incrementally observes one newly appended tracked event.

Normal `RuntimeLoop.__init__` currently does the following:

1. runs narrow interrupted-turn recovery when not in replay mode;
2. constructs `Mirror(eventlog)`, which automatically rebuilds existing ledger state;
3. constructs `MemeGraph(eventlog)`, which remains empty;
4. registers `memegraph.add_event` only for future EventLog emissions;
5. constructs and explicitly rebuilds `ConceptGraph`;
6. initializes commitment, autonomy, indexing, CTL lookup, and optional supervisor components.

There is no call to `self.memegraph.rebuild(eventlog.read_all())` in normal or replay `RuntimeLoop` initialization.

This affects both principal persisted-runtime entry points:

- the interactive CLI opens the database and constructs one default, autonomy-enabled `RuntimeLoop` for the process;
- `run_one_turn` opens the database and constructs an autonomy-disabled `RuntimeLoop` for every one-shot invocation. The MCP server launches that one-shot process for each serialized tool call.

The second path means graph history is not merely lost once per long-running restart: normal MCP use reconstructs a fresh empty shared `MemeGraph` on every tool call.

### Explicit rebuild paths that are not affected

Several production utilities create their own local `MemeGraph` and explicitly rebuild it before use:

- `pmm.runtime.context_builder.build_context`;
- deterministic reflection graph statistics;
- the indexer's graph-based CID discovery;
- commitment impact scoring;
- meta-reflection generation;
- autonomy stalled-commitment analysis;
- CLI `/graph` and `/pm graph` commands.

Those local paths do not repair `RuntimeLoop.memegraph`. Their correct use of `rebuild` cannot establish startup coverage for the shared graph consumed during a normal turn.

### Affected production consumers

#### Retrieval selection

`run_retrieval_pipeline` consumes the shared graph to:

- derive CIDs from concept-bound events through `ConceptGraph.threads_for_concept`;
- obtain bounded commitment slices through `get_thread_slice`;
- expand selected events through graph neighbors;
- obtain full commitment threads through `thread_for_cid`;
- expand commitment subgraphs through `subgraph_for_cid`.

Explicit concept-to-CID bindings survive because `ConceptGraph` rebuilds. However, the bound CID resolves to an empty thread until the corresponding graph history has been observed or explicitly rebuilt. Concept-bound events may still be selected directly, so degradation can be partial rather than an entirely empty result.

#### Model-visible rendering

`render_context_with_metrics` uses the shared graph for:

- the `## Threads` section and its commitment status/goal rows;
- the conditional `## Graph` section;
- the `context_has_graph` flag passed into base-prompt composition.

`_render_threads` can emit the `## Threads` heading even when every relevant CID has an empty slice, so an empty heading is not proof that a thread was reconstructed.

#### Cross-boundary relationships

New events after restart are observed incrementally, but relationships to pre-restart nodes cannot be added when those targets are absent:

- a new assistant can link to the new turn's user event;
- a new close for a pre-restart open cannot create its live `closes` edge, even though R08 records the exact `open_event_id` in the ledger;
- a new reflection about a pre-restart event cannot create `reflects_on` when that target node is absent;
- a new identity adoption can only infer an edge to assistant/reflection nodes present in the post-restart live graph; `MemeGraph` does not project the adoption's recorded anchor IDs directly;
- a post-restart commitment can build a complete thread only when its relevant assistant/open events were both observed after restart.

#### Lifetime memory

`maybe_append_lifetime_memory` calls `meme_graph.cids_for_event` for events in the chunk span when a graph is supplied. The normal turn supplies `RuntimeLoop.memegraph`. After restart, old span events are absent from that graph, so CID discovery through graph relationships can omit thread handles. Direct CIDs on open/close events are still collected separately.

### Failure and degradation behavior

The startup omission does not raise, append a diagnostic, or mark the graph incomplete. Consumers receive ordinary empty lists, empty stats, missing edges, or reduced provenance:

- `thread_for_cid`, `get_thread_slice`, `neighbors`, and `subgraph_for_cid` return empty lists;
- graph rendering may be omitted because the live node count is below five;
- thread expansion and graph expansion reasons disappear from retrieval provenance;
- a relationship that cannot resolve is silently absent from the live projection;
- `Mirror` and `ConceptGraph` may still expose enough state for the prompt to look partially reconstructed.

Incremental projection also has no completeness signal: `EventLog._emit` catches and suppresses listener exceptions. This is not needed to establish the startup omission, but it means a future restoration design must address both initial reconstruction failure and later listener-update failure if it claims the shared graph is complete.

The historical form remains intact in `EventLog`. An explicit full rebuild can recover the projection under current code. There is no false canonical event created by this gap; the failure is projection and retrieval degradation.

### Fresh persisted-runtime observations

#### Live graph versus reopened normal runtime

A disposable on-disk ledger was populated through `RuntimeLoop` with a defined concept, an assistant commitment, concept-to-event bindings, and a concept-to-CID binding.

Before shutdown:

- the shared graph had 9 nodes and 4 edges;
- CID `b1186ed3` had thread `[7, 16, 18]`;
- the next retrieval selected `[7, 5, 18, 16]`;
- events `18` and `16` carried `thread_expansion` and `graph_expansion` provenance.

Immediately after reopening the same ledger through normal `RuntimeLoop` construction:

- shared graph stats were 0 nodes and 0 edges;
- `Mirror` still reported CID `b1186ed3` open;
- `ConceptGraph` still resolved `topic.restart` to CID `b1186ed3`;
- `thread_for_cid("b1186ed3")` returned `[]`.

After one new post-restart turn:

- the shared graph contained only 4 new tracked nodes and 1 edge;
- the old CID thread still returned `[]`;
- retrieval selected only concept-bound events `[7, 5]`;
- the prior `thread_expansion` and `graph_expansion` provenance was absent.

The disposable database was deleted after the observation.

#### Authoritative close across the restart boundary

A second disposable ledger opened one commitment before shutdown and closed it through a production `RuntimeLoop` after reopening:

- open event: `15`;
- close event: `28`;
- close metadata retained exact `open_event_id: 15`;
- `Mirror` correctly reported the CID closed;
- the reopened runtime's live graph did not contain edge `28 -> 15`;
- an explicit `MemeGraph.rebuild(log.read_all())` reconstructed edge `28 -> 15`.

This confirms that the gap does not invalidate R08's canonical transition. It weakens the live graph projection of that valid relationship.

### Existing tests

Relevant passing tests establish:

- full rebuild and explicit incremental feeding produce equal graph edges;
- graph edge and thread helpers work after an explicit rebuild;
- retrieval and context rendering work when tests explicitly rebuild `MemeGraph`;
- R08's exact close edge appears after explicit rebuild;
- independent utilities that rebuild their own graph can consume existing history.

They do not establish:

- normal `RuntimeLoop` startup parity between a live graph and a reopened graph;
- graph-backed retrieval parity before and after process restart;
- consecutive MCP/one-shot calls retain graph-backed context;
- cross-boundary close, reflection, or identity edges appear in the shared live graph;
- incomplete shared-graph state is diagnosed.

The prior `test_replay_integrity` reloads an EventLog and rebuilds `Mirror`, then compares hash sequences. It does not construct or compare the runtime's shared `MemeGraph`.

### Authorization-required policy choices

No choice below is made by this inventory:

1. Is a complete shared graph mandatory before the first persisted-ledger retrieval, or is graph context optional enrichment?
2. Must interactive, one-shot/MCP, replay, and programmatic `RuntimeLoop` construction share the same restoration rule?
3. Should restoration replay every tracked event, use a checkpoint/snapshot, or use a bounded history? What large-ledger limit is acceptable?
4. At what point should rebuild occur relative to interrupted-turn recovery, listener registration, autonomy initialization, and possible concurrent appends?
5. Should rebuild or later listener-update failure abort startup/turn execution, append a diagnostic, quarantine graph-dependent retrieval, or silently degrade?
6. Should restored edges always use current projection logic, or must projection-version/legacy semantics be retained for historical graphs?
7. Must cross-boundary `closes`, `reflects_on`, and identity-adoption relationships be exact prerequisites for graph-backed retrieval?
8. Is rebuilding on every one-shot/MCP call acceptable, or is a longer-lived/cached projection lifecycle required?
9. What parity tests and performance ceilings must become release requirements?

### Auditor finding

Repository state: local `main` at `28d09c9e623c00f8ee9da3f3c34fe29857858834`; tracked tree clean; this inventory is the sole untracked item; one commit ahead of `origin/main` at `4ca84d6bcb25e106a620f77c9d29ef68eadc2d44`.  
Claimed guarantee: existing tracked ledger history populates the shared `RuntimeLoop.memegraph` before persisted-runtime retrieval.  
Actual mechanism: `MemeGraph` starts empty; `RuntimeLoop` registers only its incremental listener; explicit rebuild exists but is not invoked.  
Production paths: interactive CLI, one-shot CLI, MCP, replay construction, retrieval, context rendering, lifetime memory, and post-restart tracked-event listeners.  
Validation paths: not applicable; this is projection lifecycle coverage rather than candidate validation.  
Bypass or degradation paths: all normal persisted `RuntimeLoop` construction paths omit the rebuild; independent utilities rebuild only their private graph instances.  
Preserved form: complete hash-linked EventLog history, exact R08 close metadata, rebuilt `Mirror`, rebuilt `ConceptGraph`, and explicit rebuild capability.  
Promoted form: partial live graph containing only post-construction tracked events.  
Integrity tier: projection coverage and relational-integrity degradation; semantic adequacy remains unresolved.  
Coverage status: coverage gap — the applicable rebuild is not invoked by the normal shared-graph startup path.  
Enforcement status: not applicable to input validation; graph consumers do not enforce completeness before use.  
Strongest supported conclusion: persisted history is sufficient for explicit `MemeGraph` reconstruction, but normal `RuntimeLoop` startup does not perform it, so graph-backed operational continuity is partially enforced and silently weaker after restart.  
Implementation evidence: none; no runtime change was authorized or made.  
Relevant tests: graph rebuild/incremental, graph helpers, retrieval pipeline, context renderer, R08 close graph, and independent rebuild tests; none cover normal persisted startup parity.  
Post-change verification: not applicable; this is an as-is inventory.  
Proposed changes: none. The policy choices above require authorization before design or implementation.

---

## C02 — Recent conversation messages are not automatically rendered into model context

### Narrow guarantee under audit

> The previous managed user/assistant exchange is automatically included in the next production model call, independently of semantic retrieval.

The repository does not establish this guarantee.

### Production path

For each non-replay turn, `RuntimeLoop.run_turn`:

1. appends the current `user_message`;
2. optionally appends its embedding;
3. calls `eventlog.read_tail(limit=10)` and stores the result in `history`;
4. separately reads total event count and projected open commitments;
5. runs the retrieval pipeline;
6. renders only the retrieval result and projected state;
7. calls `compose_system_prompt(history, ..., history_len=total_events)`;
8. sends the rendered system prompt and current raw user input to the adapter.

`compose_system_prompt` does not inspect the content, role, ID, or order of any `history` item. Because `RuntimeLoop` supplies `history_len`, even meditation cadence uses total event count rather than `len(history)`. The recent tail's contents have no effect on the normal provider prompt.

### Retrieval does not supply a general recency fallback

The normal retrieval pipeline selects from:

- configured/sticky concept bindings and topology;
- explicit concept-to-CID bindings and `MemeGraph` thread slices;
- graph expansion;
- pinned or vector-matched lifetime-memory records and their samples;
- vector refinement over already eligible concept/thread/summary candidates.

It does not add the latest messages merely because they are recent. `RetrievalConfig.recent_event_tail` exists as a field but is not read by `run_retrieval_pipeline`.

The runtime's continuity fallback binds every turn to `identity.continuity` when no concept is declared, but the default retrieval seed is `user.identity`. `CTLLookupInjector` searches defined concept tokens. A continuity binding alone therefore does not guarantee that the next unrelated query selects the prior turn.

### Alternate compatibility path

`pmm.runtime.context_builder.build_context` explicitly rebuilds projections and, when retrieval is empty, falls back to recent user/assistant messages. Existing tests exercise that behavior.

No current production `RuntimeLoop` caller invokes `build_context`. Its tail fallback cannot establish a normal-turn guarantee.

### Affected consumers and downstream effects

The immediate consumer is the model adapter. When the prior exchange is not independently retrieved:

- the model does not receive those user/assistant words;
- the `retrieval_selection` event omits their IDs and provenance;
- prompt telemetry can report zero selected evidence events;
- evidence designations and claim `evidence_events` cannot treat those events as current-turn selected evidence, even though they exist in the ledger;
- the response may omit, repeat, contradict, or misinterpret the immediately preceding exchange;
- any later commitment, claim, identity proposal, closure, reflection, or concept binding is generated from that reduced context.

Open-commitment state, identity adoption summaries, concept definitions, or lifetime-memory samples can still convey some derived information. That is not equivalent to supplying the prior conversation.

### Failure and degradation behavior

No exception is raised. The messages remain in EventLog and remain available to export, replay, explicit retrieval, or the compatibility context builder.

When retrieval selects nothing, `context_renderer` makes the absence visible in the model prompt through `## Retrieval Selection Mechanics` and the sentence `No ledger evidence events were selected for this turn.` It omits the `## Evidence` section. A `retrieval_selection` event with `selected: []` is still appended on the normal completed path.

The omission is therefore auditable but operationally permissive: generation proceeds without an automatic conversation tail.

### Fresh persisted-runtime observations

Unique sentinel strings were used so their presence could be checked without semantic interpretation.

#### Same live runtime

Immediately before a second unrelated turn:

- `read_tail(10)` contained both `LIVE_PREVIOUS_USER_91c4` and `LIVE_PREVIOUS_ASSISTANT_91c4`;
- the provider-facing system prompt contained neither string;
- retrieval selected `[]`;
- the prompt contained the explicit empty-selection notice.

#### After persisted-ledger reopen

One turn was written, the original connection was closed, and the ledger was reopened through a new normal `RuntimeLoop`. Immediately before the follow-up:

- `read_tail(10)` contained both `RESTART_PREVIOUS_USER_91c4` and `RESTART_PREVIOUS_ASSISTANT_91c4`;
- the provider-facing system prompt contained neither string;
- retrieval selected `[]`;
- the prompt contained the same empty-selection notice.

The behavior is therefore not created by restart. It exists in a continuous live runtime and remains after reopen. Both disposable databases were deleted after observation.

### Existing tests

Relevant passing tests establish:

- the compatibility `build_context` path falls back to a recent message window;
- empty retrieval renders an explicit model-visible notice and no Evidence section;
- first-turn prompt telemetry can report zero selected evidence events;
- the normal loop's context can omit raw message text and still satisfy its integration test;
- concept, thread, summary, and vector-refinement selection work when their eligibility conditions are met.

They do not establish:

- the immediately preceding exchange is included in a normal consecutive `RuntimeLoop` turn;
- the recent tail's content affects `compose_system_prompt`;
- live and reopened turns receive the same mandatory conversational window;
- `recent_event_tail` changes pipeline behavior;
- recent-tail events participate in retrieval provenance or evidence-availability validation;
- prompt budgets preserve a required number of recent turns.

One lifetime-memory test assigns `cfg.recent_event_tail = 10`, but the production pipeline never reads that field. The test succeeds through lifetime-memory selection, not because a recent-tail limit is enforced.

### Authorization-required policy choices

No choice below is made by this inventory:

1. Should a conversational tail be mandatory, optional, configurable, or intentionally absent in favor of semantic retrieval?
2. Which records qualify: managed user/assistant terminal pairs only, generation failures, recovery events, tool/runtime output, or other event kinds?
3. Should the current just-appended user event be excluded from the tail because it is already sent separately?
4. Should the window be measured in turns, messages, event IDs, characters, or tokens? The existing `read_tail(10)` counts all event kinds, not conversation turns.
5. Should assistant control lines and structured headers be included raw, filtered, or represented separately?
6. Where should the tail be rendered, and how should duplicate events already selected by retrieval be ordered and deduplicated?
7. Must recent-tail events be added to `retrieval_selection` provenance and `selected_event_ids` so evidence designations and claim references may cite them?
8. When the prompt budget is constrained, does the conversation tail take precedence over concepts, open commitments, graph threads, lifetime memories, raw evidence, or the system primer?
9. Must live and reopened runtimes produce byte-identical tail sections for the same ledger boundary?
10. Should the existing `recent_event_tail` field and compatibility `build_context` fallback be adopted, replaced, or retired?
11. Should inability to include the required tail abort generation, append a diagnostic, or degrade with an explicit model-visible notice?
12. What adversarial-content and prompt-injection treatment applies when prior assistant/user text is reinserted as conversation rather than raw evidence?

### Auditor finding

Repository state: local `main` at `28d09c9e623c00f8ee9da3f3c34fe29857858834`; tracked tree clean; this inventory is the sole untracked item; one commit ahead of `origin/main` at `4ca84d6bcb25e106a620f77c9d29ef68eadc2d44`.  
Claimed guarantee: the immediately prior managed exchange is automatically included in the next production model call.  
Actual mechanism: `RuntimeLoop` reads ten recent events but passes their unused contents to `compose_system_prompt`; only retrieval-selected IDs are rendered.  
Production paths: interactive, programmatic, one-shot, and MCP turns through `RuntimeLoop.run_turn`; retrieval, rendering, prompt composition, adapter input, and evidence-availability validation.  
Validation paths: no conversational-tail validator exists; claim/evidence availability checks use retrieval-selected IDs only.  
Bypass or degradation paths: every normal turn can omit recent messages when no independent retrieval route selects them; `build_context` has a separate fallback that normal turns do not invoke.  
Preserved form: complete user/assistant ledger events, exports/replay, optional later retrieval, and explicit empty-selection diagnostics.  
Promoted form: provider prompt containing selected evidence and projected state but no mandatory recent conversation section.  
Integrity tier: retrieval coverage and model-context availability; semantic relevance remains unresolved.  
Coverage status: no automatic-tail guarantee is implemented; if recency is required, this is a system-wide coverage gap in the normal turn path.  
Enforcement status: not applicable until tail eligibility and availability policy are authorized; current evidence selection enforces only its existing retrieval-selected set.  
Strongest supported conclusion: PMM persistently records the conversation but does not automatically show the immediately preceding exchange to the next model call; omission is auditable and may occur both live and after restart.  
Implementation evidence: none; no runtime change was authorized or made.  
Relevant tests: compatibility tail fallback, empty selection rendering, prompt telemetry, loop context, and retrieval selection tests; none require a normal consecutive-turn tail.  
Post-change verification: not applicable; this is an as-is inventory.  
Proposed changes: none. The policy choices above require authorization before design or implementation.

---

## Verification performed for this inventory

Fresh disposable production-path observations:

- live versus reopened shared-graph state and retrieval provenance;
- authoritative close across a restart boundary, followed by explicit graph rebuild;
- prior-message presence in `read_tail(10)` versus absence from provider input, both live and after reopen.

Focused existing tests were rerun from the repository virtual environment during the continuation audit:

```text
31 passed in 0.22s
```

The selection included graph rebuild/helpers, R08 close projection, retrieval, context rendering, loop integration, prompt telemetry, and compatibility context-builder coverage. No full regression suite was requested or run because this task did not change executable code.

## Sequencing boundary

This inventory does not select either implementation. C01 has the more direct projection-continuity consequence because it can suppress exact relationships already present in canonical history, including an R08 close edge, while C02 is a prompt-availability policy whose correct window and evidence status are not yet defined.

R07 remains queued. The next action for either continuity gap is explicit authorization of its policy choices, not implementation inferred from this document.
