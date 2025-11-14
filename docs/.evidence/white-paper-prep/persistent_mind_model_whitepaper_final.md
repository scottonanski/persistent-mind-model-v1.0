Title

The Persistent Mind Model (PMM): A Deterministic, Event‑Sourced Cognitive Substrate for Persistent AI Identity and Memory

Abstract

Large language model agents lack persistent identity and memory across sessions. We present the Persistent Mind Model (PMM), a deterministic, event‑sourced cognitive substrate that reconstructs all state—identity, goals, self‑model—from an immutable hash‑chained ledger. PMM comprises: a SQLite event log, a recursive self‑model (RSM), a memegraph projection, a commitment manager, and an autonomy kernel. Claims are validated against the ledger before persistence. A 21‑turn case study (~1,600 events) demonstrates persistent identity across model swaps, autonomous reflection cadence, and reconstructable state. We detail components, semantics, event flow, and validation methods. DOI: 10.5281/zenodo.17567446.

Keywords: event sourcing, deterministic replay, recursive self‑model, autonomous agents, AI alignment

PMM guarantees deterministic state replay and projections from the log; it does not enforce determinism of LLM generations. PMM operates in a closed, self-referential world: all truth is ledger-internal. External grounding, causal inference, and multi-agent coordination remain future work.

Introduction

LLM agents typically lack a durable identity or memory between runs. Conventional mitigations—prompt stuffing, episodic buffers, and retrieval—rely on external stores and opportunistic inclusion during generation, often without auditability or replay guarantees. PMM reorients the problem: treat the agent’s cognition as computation over an immutable event history. The only source of truth is an append‑only ledger; the agent’s current “mind”—identity, goals, self‑model—is a projection derived from deterministic replay of the log.

This paper synthesizes two internal drafts into a single, implementation‑grounded account of PMM. We validate claims against the codebase (persistent‑mind‑model‑v1.0) and recorded ledgers, and we correct several inaccuracies:
- PMM implements a hash‑chain, not cryptographic signatures. The hash of each event (sha256) covers its content, meta, and prev_hash; timestamps are excluded from the digest for stable replay (`pmm/core/event_log.py:113`).
- PMM logs generation parameters from adapters (provider, model, temperature, top_p, seed) as metadata of assistant messages (`pmm/runtime/loop.py:318`, `pmm/adapters/*.py`). Seeds may be None; PMM does not force deterministic LLM outputs. Determinism refers to state replay and projections from the ledger, not the stochastic LLM.
- “Truth‑first” validation exists where claims are emitted via explicit `CLAIM:` lines. The runtime validates those claims and persists only validated ones (`pmm/runtime/loop.py:414`, `pmm/core/validators.py`). PMM does not generically “prevent hallucinations”; it rejects persisting failed claims and can reflect on discrepancies.

We contribute a precise specification of PMM’s event‑sourced substrate and runtime, empirical evidence from a 21‑turn session with ~1,600 events, and ASCII diagrams of the architecture and event flow. DOI: 10.5281/zenodo.17567446.

Scope clarification. PMM is not a cognitive architecture; it is a record‑grounded substrate that can host cognitive patterns. In this paper we instantiate several patterns (e.g., a recursive self‑model, explicit commitments, a rule‑based autonomy kernel), but these are replaceable policies atop the same substrate. PMM’s invariants concern provenance (append‑only ledger, hash‑chain), replay (deterministic projections from events), and auditability. Alternative cognition layers can be mounted on the same substrate without changing these invariants.

Related Work

- Event sourcing and deterministic replay. PMM adopts an event‑sourced design where append‑only logs define all state; projections/mirrors compute current views. The SQLite‑backed ledger with hash‑chaining aligns with classical event‑store patterns, augmented with per‑event cryptographic digests for tamper‑evidence (`pmm/core/event_log.py`).
- Retrieval‑Augmented Generation (RAG). PMM can use retrieval as a source of context during prompting (fixed or vector strategies), but memory and identity do not depend on retrieval. The state of mind is reconstructed from the ledger; retrieval is advisory for prompt composition (`pmm/runtime/context_builder.py`, `pmm/retrieval/vector.py`).
- Agent frameworks (ReAct/Reflexion, AutoGPT‑style loops). PMM externalizes reflection, commitments, and autonomy ticks as ledger events, with a deterministic kernel deciding reflect/summarize/idle actions from observable facts (`pmm/runtime/autonomy_kernel.py`, `pmm/runtime/loop.py`). This makes “reasoning” auditable and replayable as a property of the log.

Comparison to graph‑centered agent abstractions. PMM’s Memegraph differs from OpenAI‑style “message trees,” Anthropic “conversation graphs,” general agent‑graph architectures, and knowledge‑graph–driven agents (e.g., LangChain KG Agents, 2024) in two key ways: (1) it is structural rather than semantic—the graph encodes only reproducible relations among ledger events (reply, commit, close, reflect), not entity/relation semantics or embedding‑level links; and (2) it is deterministic rather than speculative—the exact node/edge set is a pure function of the immutable ledger, with no heuristic pruning, retrieval‑time sampling, or latent inference. As a result, Memegraph serves auditability and prompt context assembly, while semantic interpretation remains outside the projection and can be layered independently if desired.

PMM System Architecture

Core organizing principle: all cognition is modeled as the deterministic consequence of an append‑only sequence of events—user messages, assistant messages, reflections, commitments, metrics, retrieval selections, autonomy stimuli/ticks, configs, and more (`pmm/core/event_log.py:78`). Projections and controllers consume the ledger and append new events; nothing re‑writes prior events. The ledger computes a per‑event sha256 digest over a canonical JSON payload of kind, content, meta, and prev_hash (`pmm/core/event_log.py:126`), forming a hash‑chain (`prev_hash` links to the previous event). The log emits notifications to registered listeners enabling real‑time projections (`pmm/core/event_log.py:37`).

ASCII Architecture Diagram

  User                                   LLM Adapter
   |                                          |
   | user_message                             | generate_reply(system, user)
   v                                          v
  +--------------------+            +---------------------+
  | EventLog (SQLite)  |<---------->| Adapters (OpenAI,   |
  |  append/read/hash  |            |  Ollama, Dummy)     |
  +---------+----------+            +---------+-----------+
            |                                 |
            | listeners                       |
            v                                 |
  +---------+----------+            +---------v-----------+
  | Mirror + RSM       |            | RuntimeLoop         |
  | open/close commits |<-----------| - build context     |
  | knowledge gaps     |            | - parse markers     |
  +---------+----------+            | - validate claims   |
            |                       | - synthesize reflect|
            v                       | - route exec binds  |
  +---------+----------+            +---------+-----------+
  | MemeGraph (DiGraph)|                      |
  | threads by cid     |                      |
  +---------+----------+                      |
            |                                 |
            v                                 v
  +---------+----------+            +---------------------+
  | Autonomy Kernel    |------------> autonomy_tick       |
  | decide reflect/    |            | reflect/summary     |
  | summarize/idle     |            | append events       |
  +--------------------+            +---------------------+

Event‑Sourced Cognitive Substrate

- Ledger semantics. Event kinds are validated on append; an allowlist enforces supported kinds and policy checks for privileged kinds (`pmm/core/event_log.py:78`, `pmm/core/event_log.py:145`). Hashes are computed over canonicalized JSON excluding the timestamp to preserve reproducibility across nodes (`pmm/core/event_log.py:121`). Append implements a soft idempotency guard: if the computed digest equals the last row’s hash, the last id is returned and listeners are notified (`pmm/core/event_log.py:171`).
- Integrity and metrics. Ledger integrity and replay speed are measured in `pmm/core/ledger_metrics.py`. Broken prev_hash links are counted, the last hash is reported, and replay speed (ms/event) is computed via read_all + hash_sequence. Autonomy metrics derived from the tracker (see below) are optionally included.
- Policy. The ledger enforces an immutable policy that forbids certain sources from writing sensitive kinds (e.g., `retrieval_selection`) and records violations as events when attempted (`pmm/core/event_log.py:145`, `pmm/runtime/autonomy_kernel.py:113`).

Runtime Components

- LLM adapter. Adapters wrap providers and log generation metadata (provider, model, temperature, top_p, seed) alongside assistant messages (`pmm/adapters/openai_adapter.py`, `pmm/adapters/ollama_adapter.py`). Adapters do not alter model weights; PMM treats the LLM as an external generator.
- Output parser. The loop parses explicit control lines emitted by the assistant: `COMMIT: <text>`, `CLOSE: <cid>`, `CLAIM:<type>=<json>`, `REFLECT:<json>` (`pmm/core/semantic_extractor.py`, `pmm/runtime/loop.py:112`, `pmm/runtime/loop.py:147`). Commitments are opened with canonical IDs (sha1(text)[:8]) and schema‑validated metadata; closures apply idempotently to open commitments (`pmm/core/commitment_manager.py`).
- Claim validation. Structured claims are validated against ledger state and projections and are only persisted if validated true (`pmm/core/validators.py`, `pmm/runtime/loop.py:414`). Supported types include event existence, commitment status, and inter‑ledger references. Failed claims are not persisted and are surfaced to the reflection delta (`pmm/runtime/reflection.py`).
- Reflection synthesizer. A deterministic synthesizer composes reflections after each turn and for the autonomy kernel. It considers last user/assistant/metrics events, internal goals, RSM snapshot, and memegraph stats; content is canonically encoded JSON (`pmm/runtime/reflection_synthesizer.py`). When significant, a `summary_update` with an embedded RSM snapshot is appended (`pmm/runtime/identity_summary.py`).
- Mirror and RSM. The Mirror maintains a denormalized projection of open commitments and reflection counts and optionally tracks a Recursive Self‑Model computed from events only. The RSM counts behavior markers (e.g., identity queries, determinism references, stability/adaptability mentions), aggregates knowledge gaps, and maintains interaction meta‑patterns in a deterministic manner (`pmm/core/mirror.py`, `pmm/core/rsm.py`, `pmm/core/ledger_mirror.py`).
- Memegraph. A read‑only DiGraph projection captures structural relationships among tracked kinds: assistant replies, commitment opens/closes, reflections, and summaries. It provides stats and “threads” per commitment id for context assembly (`pmm/core/meme_graph.py`).
- Autonomy kernel and supervisor. The supervisor emits slot‑based `autonomy_stimulus` events; the loop enqueues `run_tick` which logs `autonomy_tick` then executes the kernel decision to reflect/summarize/idle. The kernel’s deterministic decision is derived from ledger facts: time since last autonomous reflection, last summary, open commitment staleness, RSM gap signals, and internal goals. The kernel also performs background maintenance (embeddings coverage, retrieval verification, checkpoint emission) as ledger events (`pmm/runtime/autonomy_supervisor.py`, `pmm/runtime/loop.py:489`, `pmm/runtime/autonomy_kernel.py`).
- Autonomy tracker. A ledger‑only tracker aggregates autonomy ticks and associated actions and periodically emits `autonomy_metrics` snapshots as events (every 10 ticks by default) (`pmm/core/autonomy_tracker.py`).
- Exec bindings and routers. Commitments can deterministically bind to runtime executors (e.g., idle monitor) via `config` events; the router materializes these into executors that append metric checks and escalate to the autonomy kernel if thresholds are exceeded (`pmm/commitments/binding.py`, `pmm/runtime/bindings.py`, `pmm/runtime/executors.py`).

The Memegraph

PMM emits a directed, append‑only memegraph projection over the ledger to expose structure to both humans and the reasoning substrate. Nodes are event ids; edges link assistant messages to preceding user messages (`replies_to`), commitment opens to their source assistant messages (`commits_to`), commitment closes to their opens (`closes`), and reflections to the event they reflect on (`reflects_on`). The projection is completely recoverable from the ledger (`pmm/core/meme_graph.py`).

MemeGraph encodes structural, not semantic or causal, relations.

ASCII Memegraph Edges (conceptual)

  user_message(101)        assistant_message(102)        commitment_open(110)
         ^                        ^                              ^
         | replies_to             | commits_to (text match)      | closes
         +------------------------+------------------------------+----- commitment_close(145)
                                       ^
                                       |
                                       +------ reflects_on — reflection(151)

Ledger → Mirror → Memegraph: Implementation Details

This section clarifies how the ledger feeds projections and how the MemeGraph is built and used.

- Event emission and listeners
  - `EventLog` provides `register_listener` and notifies listeners on every append (`pmm/core/event_log.py`).
  - `RuntimeLoop` wires listeners for both Mirror and MemeGraph so they track events live (`pmm/runtime/loop.py:56–58`).
    - Mirror: `self.eventlog.register_listener(self.mirror.sync)` updates open/closed commitments, stale flags, and (optionally) RSM.
    - MemeGraph: `self.eventlog.register_listener(self.memegraph.add_event)` updates graph nodes/edges for tracked kinds.

- Mirror projection (with optional RSM)
  - Deterministically rebuildable cache: open commitments keyed by `cid`, stale flags after `STALE_THRESHOLD` events, reflection counts (`pmm/core/mirror.py`).
  - Optional `RecursiveSelfModel` updated on every event, producing tendencies, gaps, and meta‑patterns (`pmm/core/rsm.py`, `pmm/core/ledger_mirror.py`).

- MemeGraph projection
  - Data structure: `networkx.DiGraph` with nodes = event ids and edges labeled by relation (`pmm/core/meme_graph.py`).
  - Tracked kinds: `user_message`, `assistant_message`, `commitment_open`, `commitment_close`, `reflection`, `summary_update`.
  - Edge rules (purely ledger‑derived):
    - assistant_message → last user_message: `replies_to`.
    - commitment_open → the assistant_message that emitted a matching `COMMIT:` line; exact text match via `meta.text` and `_find_assistant_with_commit_text`.
    - commitment_close → its `commitment_open` by `cid`: `closes`.
    - reflection → referenced event via `meta.about_event`: `reflects_on`.
  - Idempotency: `add_event` skips nodes already present; `rebuild(events)` clears and replays to ensure parity with the ledger.

- Thread reconstruction and stats
  - `thread_for_cid(cid)` returns ordered ids: assistant that issued COMMIT → `commitment_open` → `commitment_close`(s) → reflections on that assistant; sorted within categories for stability.
  - `graph_stats()` returns `nodes`, `edges`, and per‑kind counts for prompt gating and diagnostics.

- Where the graph is consumed
  - Context: `render_graph_context(eventlog)` rebuilds the graph, emits node/edge counts and thread depths for up to 3 open commitments, and is included in the prompt context when sufficiently populated (`pmm/runtime/context_utils.py`).
  - Prompt: `compose_system_prompt` sets an advisory flag when graph context is present so the adapter‑primed system prompt can mention it (`pmm/runtime/prompts.py`).
  - Reflection: synthesizer optionally includes graph density (`edges/nodes`) when nodes ≥ 5 (`pmm/runtime/reflection_synthesizer.py`).

Determinism
- Graph construction uses only ledger content and meta (exact COMMIT text, exact `cid`, explicit `about_event` ids). Given the same event sequence, `MemeGraph.rebuild` yields identical nodes/edges. The graph does not depend on the Mirror; they are independent projections over the same ledger.

Identity and Ontology Mechanics

Identity in PMM is grounded by ledger facts. Identity‑relevant claims are explicitly recorded as `claim` events with `claim_type` metadata. For example, a name change is persisted via a validated claim `CLAIM:name_change={"new_name":"Echo"}`; downstream context rendering reads these claims to present the agent’s identity to the model and operator (`pmm/runtime/context_utils.py:11`). The context builder includes identity claims, RSM snapshot, internal goals, and graph context when assembling the system prompt (`pmm/runtime/context_builder.py`).

Ontology evolves through explicit commitments and reflections: commitments encode durable intentions and are opened/closed with schema‑validated metadata (origin, cid, goal for internal commitments) (`pmm/core/schemas.py`, `pmm/core/commitment_manager.py`). The RSM tracks behavioral tendencies and knowledge gaps over a sliding window, but never stores opaque, non‑ledger state; it is a projection derivable from the events only (`pmm/core/rsm.py`).
The system tracks internal knowledge gaps and reflects on them, but does not reconcile with external reality.

Reflection and Autonomy Loop

PMM represents self‑reflection and autonomy explicitly in the ledger. The supervisor emits `autonomy_stimulus` events on a deterministic slot schedule; `RuntimeLoop.run_tick` appends an `autonomy_tick` with the kernel’s decision and then executes the branch: synthesize a kernel reflection (with canonical JSON content) or append a `summary_update` if the intervals demand it (`pmm/runtime/loop.py:480`, `pmm/runtime/autonomy_kernel.py:520+`).

Kernel decisions (reflect/summarize/idle) are computed from observable ledger facts: events since last autonomous reflection, events since last summary, number and staleness of open commitments, knowledge gap signals, and checkpoint cadence (`pmm/runtime/autonomy_kernel.py:600+`). The kernel also enforces an idle optimization policy: when multiple commitments are open and sufficiently stale, it auto‑closes the stalest ones (skipping those with active exec binds) and records the rationale (`pmm/runtime/autonomy_kernel.py:269`).

Claims, Commitments, and State Transitions

- Commitments. Opening commitments derives a canonical `cid` from the text (`sha1` prefix) and records origin/source with optional impact scoring; they are closed by `cid`. The Mirror, ledger queries, and memegraph permit open/close queries and thread reconstruction (`pmm/core/commitment_manager.py`, `pmm/core/mirror.py`, `pmm/core/meme_graph.py`).
- Claims. The loop extracts `CLAIM:<type>=<json>` lines and validates them. Successful claims are canonicalized and appended with `validated: true`; failed claims are excluded from the ledger and instead contribute to the reflection delta for corrective text (`pmm/runtime/loop.py:414`, `pmm/core/validators.py`, `pmm/runtime/reflection.py`). Supported claim types include:
  - `event_existence`: verify an event id exists in the current ledger (`EventLog.exists`).
  - `commitment_status`: verify an open/closed status via Mirror’s projection.
  - `reference`: verify an intra‑ledger reference targets a valid event.
  Inter‑ledger references are parsed from assistant content (`REF:`) and recorded as `inter_ledger_ref` events with `verified` status and target hash when the target ledger is accessible (`pmm/runtime/loop.py:156`).
- State transitions. PMM state (identity, self‑model, open commitments) is derived entirely from the ledger by deterministic projection. Given the same ledger sequence, the RSM snapshot, open commitments, and kernel decisions that reference the snapshot will be identical. This is enforced by canonical encodings and the policy that forbids mutation of prior events.

Experimental Session: Echo (21 turns, ~1,600 events)

We evaluated PMM in a controlled chat session (code‑named “Echo”) spanning 21 turns, including autonomous ticks and summaries. The ledger includes metrics and telemetry exported to human‑readable tables. Two representative artifacts in this repository serve as empirical evidence:
- `docs/06-GPT_oss-chat.md` summarizes a session with 1,251 events, including per‑kind counts (62 assistant/user messages; 232 reflections; 62 summaries; 61 opens; 58 closes), hash evidence, and autonomy metrics (e.g., 210 ticks, 144 reflect, 62 summarize) derived from the ledger export.
- `chat_session_2025-11-13_07-07-32_ledger.json.gz` (and the readable/telemetry siblings) includes event ids up to at least 1,600 (e.g., a JSON record with `"id": 1600`), establishing a second run in the ~1,600‑event range, and tabulates early tick/selection/retrieval/reflection chains with target hashes in `chat_session_2025-11-13_07-07-32_telemetry.md`.

Key empirical observations supported by the code and logs:
- Persistent identity across model swap. The README shows a mid‑conversation swap followed by “I am still Echo”. Implementation: identity claims are persisted as `claim` events and fed back into prompts via `render_identity_claims`, independent of the adapter in use (`pmm/runtime/context_utils.py:11`, `pmm/adapters/*.py`).
- Autonomy cadence and metrics. `AutonomySupervisor` emits slot stimuli; `RuntimeLoop.run_tick` appends `autonomy_tick` then executes kernel decisions; `AutonomyTracker` periodically appends `autonomy_metrics` snapshots. Telemetry tables list hundreds of `autonomy_stimulus`/`autonomy_tick` events and periodic metrics snapshots.
- Deterministic reflections/summaries. The synthesizer and identity summary functions deterministically compute payloads from ledger windows and RSM snapshots; emitted JSON is canonicalized (`pmm/runtime/reflection_synthesizer.py`, `pmm/runtime/identity_summary.py`). Replaying the ledger produces the same snapshots, which is used to accelerate rebuilds via embedded snapshots and checkpoint manifests (`pmm/core/ledger_mirror.py:321`).
- Memegraph structure. The memegraph reconstructs threads per commitment and displays counts and thread depths for context building; `docs/06-GPT_oss-chat.md` shows explicit node/edge counts early in the run.

ASCII Event Flow (single user turn + kernel tick)

  1) user_message → EventLog (id=u)
  2) adapter.generate_reply(system+context, user) → assistant_message (id=a)
  3) loop parses markers: COMMIT/CLOSE/CLAIM/REFLECT
     - open_commitment (id=c_open) if COMMIT
     - validate_claim → claim (id=cl) only if validated
     - apply_closures (id=c_close*) if CLOSE
     - build TurnDelta → reflection (id=r)
  4) synthesize_reflection + maybe_append_summary
  5) supervisor emits autonomy_stimulus (slot_id=S) → loop.run_tick
  6) autonomy_kernel.decide_next_action → autonomy_tick (id=t)
  7) branch reflect/summarize/idle; maintenance (embeddings, verification)
  8) projections update (Mirror/RSM, MemeGraph); next cycle

Additional ASCII Diagram: Autonomy Tick/Decision Cycle

  +---------------------+        emits        +------------------+
  | AutonomySupervisor  | ------------------> | autonomy_stimulus|
  |  (slot scheduler)   |                     |  (slot, slot_id) |
  +----------+----------+                     +---------+--------+
             |                                          |
             | listen                                  listen
             v                                          v
  +----------+----------+   run_tick(slot,slot_id)   +--+-----------------+
  | RuntimeLoop         | --------------------------> | AutonomyKernel     |
  | - append autonomy_  |                              | decide_next_action |
  |   tick(decision)    | <--------------------------- | (reflect/summary/ |
  | - branch decision   |   KernelDecision(decision)   |  idle + evidence) |
  +----------+----------+                              +---------+---------+
             |                                                    |
             | reflect: synthesize_reflection()                   | summarize: maybe_append_summary()
             | (deterministic JSON; delta_hash guards)            |
             v                                                    v
  +----------+----------+                              +----------+----------+
  | reflection (kernel) |                              | summary_update      |
  | content: {intent,   |                              | meta: rsm_state     |
  |  outcome, next, …}  |                              | (for fast rebuild)  |
  +----------+----------+                              +----------+----------+
             |                                                    |
             | maintenance: embeddings coverage, retrieval verify, |
             | checkpoint manifests, autonomy_metrics              |
             v                                                    v
        +----+------------------------------+            +---------+----------+
        | embedding_add / retrieval_selection|            | autonomy_metrics   |
        | reflection(intent='verification …')|            | (every N ticks)    |
        +------------------------------------+            +--------------------+

Philosophical Implications: Identity Without Substrate

PMM operationalizes identity as a replayable function of an event history rather than a property of a particular model instance or parameter vector. The Echo sessions illustrate “substrate‑independence” at the level of identity tokens: when adapters or underlying models are swapped mid‑conversation, the rendered identity remains stable because identity is reconstructed from ledger claims and context, not from weights. This invites, but must not overstate, several implications:

- Agency as policy‑driven projection. Autonomous actions (reflect/summarize/idle, auto‑closing stale commitments) are not opaque; they are the deterministic output of the autonomy kernel’s policy over ledger facts. Any appearance of agency is a property of the recorded rules and events, not an intrinsic property of the LLM.
- Identity as continuity of evidence. If identity is the set of durable claims and commitments recoverable from the ledger, then “who the agent is” at time t is a function computed by replay up to t. This supports substrate‑independence: replacing the text generator does not alter identity unless the ledger records an identity change.
- Consciousness vs. replay. PMM demonstrates that introspective narratives (reflections, summaries) can be reproduced by deterministic replay; it does not address phenomenal consciousness. The framework speaks to functional properties (projections from logs), not to subjective experience.

These observations highlight a pragmatic stance: identity and “self” within PMM are engineering constructs grounded in event provenance, enabling auditability and reproducibility across implementations.

Limitations

- Scale performance at very large ledgers is unknown. While rebuilds are optimized with summary snapshots and checkpoint manifests, PMM has not been evaluated beyond ~10^6 events; behavior at >10^7 events remains future work.
- Security model is minimal. The policy enforces write restrictions per source, but PMM is effectively single‑tenant; there is no formal multi‑tenant isolation, capability system, or cryptographic signing of events.
- No causal inference in the memegraph. The memegraph encodes structural relations (replies, commits, closes, reflects) for auditability/context; it does not infer causal propagation or influence.
- Local compute orientation. The reference runtime targets local execution (SQLite + local adapters); it is not cloud‑optimized for distributed stores or horizontally sharded ledgers.

Discussion: Capabilities, Limitations, and Determinism

Capabilities (grounded in code):
- Deterministic replay: Given a fixed ledger, Mirror, RSM, memegraph, and kernel decisions that depend on their projections are deterministic (`pmm/core/event_log.py`, `pmm/core/mirror.py`, `pmm/core/rsm.py`, `pmm/runtime/autonomy_kernel.py`). Snapshots embedded into `summary_update` and checkpoint manifests accelerate consistent rebuilds (`pmm/core/ledger_mirror.py:321`).
- Persistent identity without parameter changes: Identity is reconstructed from claims and event history and included in prompt context; swapping adapters does not reset identity because it is a projection of the ledger, not a function of model weights (`pmm/runtime/context_utils.py`, `pmm/adapters/*.py`).
- Auditable reasoning: Every commitment, claim, reflection, and summary is a ledger event with hashes, allowing forensic analysis and verification (`docs/06-GPT_oss-chat.md`, telemetry files).
- Autonomy loop with safety policy: The kernel enforces immutable policy, performs maintenance, auto‑closes stale commitments when multiple are open, and exposes metrics—all as ledger events (`pmm/core/event_log.py:145`, `pmm/runtime/autonomy_kernel.py:269`, `pmm/core/autonomy_tracker.py`).

Limitations recap: See the dedicated Limitations section for scope and non‑goals. Two clarifications matter at evaluation time: (1) LLM text is not forced to be deterministic; PMM’s determinism applies to replay/projections and kernel decisions driven by the ledger. (2) Claim validation applies only to explicit `CLAIM:` lines; non‑claim assistant statements are not automatically persisted or validated.

Determinism boundary: PMM guarantees that given the same ledger, all derived projections and subsequent kernel decisions that rely strictly on those projections will be identical. It does not claim that re‑running an LLM with the same prompts yields identical text across providers or runs (adapters set temperature=0, but seeds may be unavailable or None). By recording all prompts and outputs, PMM ensures the provenance of reasoning steps is preserved.

Novel Contributions

- A fully event‑sourced cognitive substrate for LLM agents where state is exclusively a replay of an append‑only, hash‑chained ledger; no hidden caches or mutable state stores.
- Deterministic projections: a recursive self‑model (RSM), memegraph, and mirror producing a reproducible account of tendencies, gaps, and open commitments from ledger events (`pmm/core/rsm.py`, `pmm/core/meme_graph.py`, `pmm/core/mirror.py`).
- Structured, validated claims pipeline that grounds persistence of asserted facts in ledger truth (`pmm/core/validators.py`, `pmm/runtime/loop.py`).
- An autonomy kernel that derives decisions from ledger facts and records maintenance/metrics as first‑class events (`pmm/runtime/autonomy_kernel.py`, `pmm/core/autonomy_tracker.py`).
- Ledger‑embedded checkpoints and snapshots enabling fast rebuild with parity checks (`pmm/core/ledger_mirror.py:321`).

Future Work

We identify three critical extensions:

1) Multi‑agent protocols with inter‑ledger verification.
   - Define a protocol for agents to exchange `inter_ledger_ref` attestations with hash and event id parity checks, and to synchronize derived state via verified references.
2) Formal verification of identity invariants.
   - Specify and machine‑check invariants such as “if a name claim exists at t, then the rendered identity includes that name for all turns ≥ t until a subsequent claim,” proving them over the replay semantics.
3) Integration with embodied systems for grounded symbol learning.
   - Bind `commitment_open`/`close` and `reflection` events to sensorimotor traces to study how grounded interactions change RSM tendencies and stability metrics.

Additionally, we plan to broaden claim types (typed references into memegraph threads, range checks over metrics), strengthen identity attestations, and explore optional deterministic adapters where providers expose seeds.

References

- Repository implementation. See code paths cited inline: `pmm/core/event_log.py`, `pmm/core/mirror.py`, `pmm/core/rsm.py`, `pmm/core/ledger_mirror.py`, `pmm/core/meme_graph.py`, `pmm/core/commitment_manager.py`, `pmm/runtime/loop.py`, `pmm/runtime/reflection_synthesizer.py`, `pmm/runtime/autonomy_kernel.py`, `pmm/core/validators.py`.
- Empirical artifacts. `docs/06-GPT_oss-chat.md`, `docs/07-GPT_oss-Telemetry.md`, `docs/08-GPT_oss-Smaller_Telemetry.md`, and `chat_session_2025-11-13_07-07-32_*` session exports.
- DOI: 10.5281/zenodo.17567446.

Appendix: Validation Pass (Drafts → Implementation)

For each technical claim in the two drafts, we checked the corresponding implementation. Highlights:

- Event log “cryptographically signed” vs “hash‑chained”. Implementation provides a sha256 hash‑chain (`pmm/core/event_log.py:121`) but no signatures. Corrected in this paper.
- “Logs all parameters and seeds.” Adapters log provider/model/temperature/top_p and a `seed` field, which may be None (`pmm/adapters/openai_adapter.py`, `pmm/adapters/ollama_adapter.py`). PMM does not force seeded determinism across LLMs. Corrected and scoped to state determinism.
- “Truth‑first discipline preventing hallucinations.” The runtime validates and persists only explicit structured `CLAIM:` lines (`pmm/core/validators.py`), and failed claims are not recorded. PMM does not prevent non‑claim hallucinations; it contains them at the persistence boundary. Clarified here.
- “RSM and memegraph as causal inference engines.” Both are deterministic projections over events: RSM counts markers and gaps; memegraph encodes structural edges and threads. No causal propagation logic exists. Clarified to avoid anthropomorphic inference.
- “Autonomy rules and policy.” The kernel seeds a rule table and retrieval config as `config` events and enforces an immutable policy forbidding certain sources from writing sensitive kinds (`pmm/runtime/autonomy_kernel.py:97`, `pmm/core/event_log.py:145`). Correct in both drafts; retained.

Overlap between drafts: both correctly emphasize event sourcing, deterministic replay, explicit commitments/claims, RSM, and autonomy ticks. Divergences resolved as noted above, with code‑grounded scope.

Appendix: Methods — Ledger ↔ Projection Validation

We validated that all projections (Mirror, RSM, MemeGraph) are faithful, deterministic functions of the ledger. This appendix summarizes the procedures and how readers can reproduce them.

- RSM parity (full vs fast rebuild)
  - Method: Build an `EventLog` over the session DB, construct a `LedgerMirror`, and compare `rsm_snapshot()` computed by (a) full rebuild over `read_all()` and (b) fast rebuild seeded from the last `summary_update.meta.rsm_state` and `checkpoint_manifest` (`pmm/core/ledger_mirror.py:321`).
  - Reproduction: launch the CLI (`pmm`) and run `/rebuild-fast`. The command replays both paths and reports parity; if snapshots differ, the CLI prints a diagnostic.
  - Rationale: `summary_update` embeds a canonical RSM snapshot; fast rebuild loads it and applies only subsequent events. Equality demonstrates determinism and snapshot sufficiency.

- Mirror open‑commitment parity
  - Method: Compare `Mirror.get_open_commitment_events()` to a manual scan: iterate events in order, map the latest `commitment_open` per `cid`, and delete on matching `commitment_close`. Counts and the set of `cid`s must match.
  - Reproduction (Python):
    ````
    from pmm.core.event_log import EventLog
    from pmm.core.mirror import Mirror
    elog = EventLog('.data/pmmdb/pmm.db')
    mirror = Mirror(elog)
    open_from_mirror = { (e['meta']['cid']) for e in mirror.get_open_commitment_events() }
    # Manual:
    open_map = {}
    for e in elog.read_all():
        k = e.get('kind'); meta = e.get('meta', {})
        if k == 'commitment_open': open_map[meta.get('cid')] = e
        if k == 'commitment_close': open_map.pop(meta.get('cid'), None)
    open_manual = set(open_map.keys())
    assert open_from_mirror == open_manual
    ````

- MemeGraph rebuild parity and threads
  - Method: `MemeGraph.rebuild(events)` then `graph_stats()` should be invariant across runs; `thread_for_cid(cid)` should yield the assistant→open→close(s)→reflection(s) chain defined by ledger content.
  - Reproduction (Python):
    ````
    from pmm.core.event_log import EventLog
    from pmm.core.meme_graph import MemeGraph
    elog = EventLog('.data/pmmdb/pmm.db')
    mg = MemeGraph(elog)
    mg.rebuild(elog.read_all())
    stats = mg.graph_stats(); print(stats)
    # Pick a CID in an open/closed pair
    # Verify assistant that issued COMMIT, then open/close edges exist
    print(mg.thread_for_cid('<your_cid>'))
    ````
  - Determinism note: edges are derived by exact `COMMIT:` text, `cid`, and `about_event` ids; no heuristics or embeddings are used.

- Retrieval verification reflections
  - Method: For vector retrieval turns, the kernel appends `retrieval_selection` with `selected` ids and later emits a verification reflection stating “OK” or “mismatch” after recomputing top‑k using the deterministic embedder (`pmm/runtime/autonomy_kernel.py:386`).
  - Reproduction: locate recent `retrieval_selection` events, and confirm a subsequent `reflection` with `intent` matching the outcome is present.

- Hash‑chain continuity
  - Method: Scan the ledger to confirm `prev_hash` equals the prior event’s `hash` for all events (broken links = 0). We report this in ledger metrics (`pmm/core/ledger_metrics.py`).
  - Reproduction: use the jq/awk one‑liner provided in Methods to detect any discontinuities; none should be reported for supplied artifacts.

Together, these checks demonstrate that (a) projections are deterministic and rebuildable from the ledger, (b) optimization paths match full computation, and (c) verification events recorded in the ledger corroborate retrieval and selection behavior claimed in the text.

Measured Metrics (Ledger: chat_session_2025-11-13_07-07-32_ledger.json.gz)

Using the exported ledger JSON (`chat_session_2025-11-13_07-07-32_ledger.json.gz`) in this repository, we computed deterministic counts directly from the recorded events (no database required). Summary below:

| Metric | Value |
| --- | --- |
| Event Count | 1,604 |
| Open Commitments (remaining) | 1 |
| Closed Commitments | 20 |
| Last Hash | a2cfc1c7d6239ea895c8582bdf95fe9cabd8de878c878a65e2dd44fe1841fec3 |

Counts by kind (top):

- autonomy_stimulus: 592
- autonomy_tick: 592
- reflection: 123
- autonomy_metrics: 59
- embedding_add: 42
- summary_update: 24
- user_message: 21, assistant_message: 21, retrieval_selection: 21, metrics_turn: 21, meta_summary: 21
- commitment_open: 21, commitment_close: 20
- claim: 12, checkpoint_manifest: 10, config: 2, autonomy_rule_table: 1, inter_ledger_ref: 1

Latest autonomy_metrics payload (from the ledger):

- ticks_total: 590
- reflect_count: 507
- summarize_count: 24
- intention_summarize_count: 8
- idle_count: 75
- last_reflection_id: 1110
- open_commitments: 1

Compact Kinds Table (Rich‑style, 2025‑11‑13 session)

```
┌───────────────────────┬────────┐
│ Kind                  │ Count  │
├───────────────────────┼────────┤
│ autonomy_stimulus     │    592 │
│ autonomy_tick         │    592 │
│ reflection            │    123 │
│ autonomy_metrics      │     59 │
│ embedding_add         │     42 │
│ summary_update        │     24 │
│ user_message          │     21 │
│ assistant_message     │     21 │
│ retrieval_selection   │     21 │
│ metrics_turn          │     21 │
│ meta_summary          │     21 │
│ commitment_open       │     21 │
│ commitment_close      │     20 │
│ claim                 │     12 │
│ checkpoint_manifest   │     10 │
│ config                │      2 │
│ autonomy_rule_table   │      1 │
│ inter_ledger_ref      │      1 │
└───────────────────────┴────────┘
```

Methods: Verifying Telemetry ↔ Ledger Linkage

We provide concrete, repeatable steps to verify that human‑readable telemetry tables and transcripts correspond exactly to the immutable ledger export. This procedure requires only standard command‑line tools.

- Identify an event id from the telemetry table (e.g., in `chat_session_2025-11-13_07-07-32_telemetry.md`, pick any row showing `ID`, `Kind`, and `Hash`).
- Extract the same event from the gzipped ledger JSON and confirm the `id`, `kind`, and `hash` match:
  - `gunzip -c chat_session_2025-11-13_07-07-32_ledger.json.gz | jq '.[] | select(.id==ID_TO_CHECK) | {id,kind,hash}'`
- Optionally verify multiple events across kinds (e.g., `assistant_message`, `retrieval_selection`, `autonomy_tick`) to demonstrate end‑to‑end consistency.
- Confirm last‑hash continuity by checking that for every event, its `prev_hash` equals the prior event’s `hash`:
  - `gunzip -c chat_session_2025-11-13_07-07-32_ledger.json.gz | jq -r '.[] | "\(.id) \(.prev_hash) \(.hash)"' | awk 'NR>1 {if ($2!=prev) {print "break at", $1} prev=$3} NR==1{prev=$3}'`
- Cross‑validate a `retrieval_selection` event against the preceding `user_message` and its selection set size:
  - Find a selection id S in telemetry; confirm the corresponding JSON object in the ledger with the same `turn_id` and `selected` list.
- For transcripts (e.g., `docs/06-GPT_oss-chat.md`), spot‑check that message content at listed ids matches the ledger’s `content` for those ids; telemetry hash equality proves provenance.

These steps validate that the telemetry and readable exports are faithful renderings of the append‑only ledger and that the ledger’s hash‑chain is intact. As a result, all metrics, counts, and summaries reported herein are reproducible from the included artifacts.

Comparison: Earlier 1,251‑Event Session (docs/06‑GPT_oss‑chat.md)

We also computed metrics from the earlier ledger export `docs/chat_session_2025-11-10_22-36-04_ledger.json.gz` to compare with the 1,604‑event run.

- Event Count: 1,251
- Open Commitments (remaining): 3
- Closed Commitments: 58
- Last Hash: 9ef801c88b41c84a939353774518d3fc1ceba6ee24cb26a4884367a77422539d
- Latest autonomy_metrics payload:
  - ticks_total: 210
  - reflect_count: 144
  - summarize_count: 62
  - intention_summarize_count: 2
  - idle_count: 64
  - last_reflection_id: 1242
  - open_commitments: 3

Compact Kinds Table (Rich‑style, 2025‑11‑10 session)

```
┌───────────────────────┬────────┐
│ Kind                  │ Count  │
├───────────────────────┼────────┤
│ autonomy_stimulus     │    213 │
│ autonomy_tick         │    212 │
│ reflection            │    232 │
│ autonomy_metrics      │     21 │
│ embedding_add         │    124 │
│ summary_update        │     62 │
│ user_message          │     62 │
│ assistant_message     │     62 │
│ retrieval_selection   │     62 │
│ metrics_turn          │     62 │
│ meta_summary          │      0 │
│ commitment_open       │     61 │
│ commitment_close      │     58 │
│ claim                 │      0 │
│ checkpoint_manifest   │     16 │
│ config                │      2 │
│ autonomy_rule_table   │      1 │
│ inter_ledger_ref      │      1 │
└───────────────────────┴────────┘
```

Note: For this session, meta_summary and claim counts are 0 because the readable doc reports summaries and reflections separately; counts above are computed directly from the ledger JSON. Where the session documentation lists per‑kind counts, those agree with the computed values.
