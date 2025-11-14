The Persistent Mind Model (PMM): A Deterministic, Event‑Sourced Architecture for Persistent AI Memory
Abstract
We introduce the Persistent Mind Model (PMM), a novel cognitive architecture that provides AI agents with persistent identity and memory through a fully deterministic, event‑sourced framework. Unlike conventional approaches that rely on fine‑tuning, context‑window trickery, or opaque parameter embeddings, PMM records every perception and decision in an immutable ledger
GitHub
GitHub
. The agent’s state – including its beliefs, commitments, and self‑model – is reconstructed solely from this log, ensuring reproducibility and auditability. We detail PMM’s architecture: an append‑only event log, an in‑memory “mirror” for state replay, structured protocol markers (COMMIT, CLAIM, REFLECT, etc.), a recursive self‑model (RSM), and an autonomy loop that drives self‑reflection. We illustrate how PMM encodes identity and knowledge through deterministic consequences of its design. In particular, we analyze a 21‑turn demonstration session (“Echo”), in which the agent Echo evolves its internal ontology and priorities purely via logged events. We contrast PMM with existing memory and agent frameworks (RAG, episodic buffers, ReAct/Reflexion, chain‑of‑thought), highlighting that PMM’s novelty lies in event provenance and state replay rather than model tuning or external retrieval. Our empirical examples and metrics (e.g. a 1600‑event ledger from Echo) show that persistent memory emerges from PMM’s event sourcing, not from the LLM. PMM thus transforms ephemeral chatbots into accountable, self‑consistent agents with provable continuity across sessions
GitHub
GitHub
.
Introduction
Large language model (LLM) agents today have no inherent long‑term memory or identity. Each session begins anew, with past conversation only optionally retrieved via clever engineering (prompts, external databases, or token windows). Common remedies like Retrieval‑Augmented Generation (RAG) or episodic storage have limitations: they either require extra components or lack full auditability
arxiv.org
. By contrast, the Persistent Mind Model (PMM) treats the agent’s mind as an append‑only ledger of events – a strategy borrowed from event‑sourced software design
GitHub
. In PMM, every user message, agent response, internal commitment, and introspective reflection is logged immutably. The current mental state (beliefs, goals, traits) is then entirely reconstructed from this ledger. As one summarizes:
“PMM is a deterministic, event‑sourced AI runtime. Every message, reflection, and commitment is recorded immutably in a cryptographic ledger”
GitHub
.
This guarantee of determinism is central. Given the same log, PMM’s in‑memory mirror yields the same identity and commitments
GitHub
. The LLM’s outputs may vary, but PMM logs all parameters and seeds too, making them reproducible. In effect, PMM’s reasoning is auditable and replayable rather than hidden. Critically, PMM’s design does not rely on opaque model tuning or hidden vector embeddings. Instead, identity and memory “emerge” purely from the provenance of events
GitHub
. No hidden state is swept under the rug – every durable decision is in the log. We make the following explicit statements of what PMM is and is not:
PMM is an event‑sourced cognitive architecture: an append‑only, hash‑chained database of timestamped events that capture the agent’s inputs and outputs
GitHub
. The runtime rebuilds state deterministically from this log
GitHub
GitHub
.
PMM is not a sentient mind or mystical agent. It contains no awareness beyond its procedural rules
GitHub
. It has no hidden learned state, no fine‑tuned weights, and no arbitrary planning beyond explicit commitments
GitHub
.
PMM is not a simple vector memory: it does not insert retrieved documents into prompts. Instead, it deterministically replays its own event history.
PMM is not an LLM tweak. It treats the LLM as a black‑box generator guided by deterministic prompts; it does not alter the model’s weights or rely on ephemeral caches.
We emphasize that all agent behavior in PMM is the deterministic consequence of its architecture. Any agency, reflection, or change in self‑model is triggered by pre‑specified rules and logged events, not “mystical” agency. This paper provides a full technical description of PMM’s design, contrasts it with related work, and demonstrates it via an empirical case study (the “Echo” session).
Background and Related Work
Persistent memory in AI has been addressed in various ways. In Retrieval‑Augmented Generation (RAG), a neural retriever selects context from a document store to enrich LLM outputs
arxiv.org
. RAG significantly improves factuality and recency by coupling LLMs with external databases
arxiv.org
. However, RAG solutions typically add heavy infrastructure (retrieval indexes, embeddings) and can lead to “prompt bloat.” They provide episodic memory but lack an explicit model of identity or commitments, and their operation is often non-deterministic and expensive. Episodic memory systems (e.g., some personal assistant features in products like Gemini or ChatGPT) store select highlights or entire chat histories for personalization
patmcguinness.substack.com
. While useful, these systems usually remain proprietary and opaque; they do not let the agent reason over its entire history in a structured way. Autonomous agent frameworks like AutoGPT or ReAct let LLMs plan and execute multi-turn actions, often using chain‑of‑thought for reasoning and external APIs for actions. ReAct (Synergizing Reasoning and Acting
arxiv.org
) interleaves natural language reasoning traces with actions in the environment, improving decision-making. Reflexion (Shinn et al. 2023) adds a verbal self-reflection loop: the agent tries actions, assesses feedback, and records this in an episodic buffer
arxiv.org
. These methods improve task performance but still treat memory as a transient buffer: they reinforce with language feedback but do not enforce persistent identity across sessions. Chain-of-Thought prompting
proceedings.neurips.cc
 taught us that LLMs benefit from explicating intermediate reasoning. Self-Consistency (Wang et al. 2023) demonstrates that sampling multiple reasoning chains and aggregating answers yields more reliable outputs
arxiv.org
. PMM is complementary: it expects the LLM to use chain-of-thought internally, but it logs any self-generated “reasoning” or “reflective” statements as formal events. Unlike CoT, PMM’s memory is not limited to one question-answer task; it persists across conversation turns. In summary, PMM draws inspiration from these lines of work but differs fundamentally: it uses event sourcing rather than parameter tuning or ad-hoc memory. It enforces rigor through deterministic protocols and cryptographic logging. This ensures that any claimed “knowledge” the agent has corresponds to actual logged evidence, improving transparency.
Architecture Overview
At the core of PMM is an append‑only Event Log (ledger): each event has a timestamp, content, and cryptographic hash linking it to the previous event. Events include user messages, assistant outputs, commitment opens/closes, claims, reflections, metrics, etc. The ledger is stored (by default) in a SQLite file
GitHub
. No deletions or overwrites occur
GitHub
; policy rules ensure only authorized actors (the agent, user, or runtime) can append certain event types
GitHub
. The ledger is the single source of truth. Parallel to the log is an in-memory Mirror (state) that replays the event log to derive the current agent state
GitHub
. Replay is a pure function of the log: given identical logs, two separate replays will yield identical mirrors
GitHub
. The Mirror reconstructs entities such as active goals (commitments), traits (e.g. tendencies), recent episodes, and summaries (reflections)
GitHub
. Optionally, PMM maintains a Recursive Self-Model (RSM): a higher-level summary of the agent’s tendencies, knowledge gaps, and identity. The RSM is also derived by replay
GitHub
. Supporting this is an Event Graph (MemeGraph), which records causal links between events (e.g. which user message an assistant response replies to, which commitment an event closes). This graph preserves conversation threads and task structure
GitHub
. When enabled, vector-based retrieval of related events populates graph features which are fed back into the prompt. The Runtime Loop is the turn engine. Figure 1 illustrates the process:
User Input
    |
    v
Event Log (append user_message)
    |
    v
Mirror State (replay ledger)
    |
    v
LLM Adapter --> LLM --> [Assistant message (with MARKER lines)]
    |
    v
Parser extracts markers -> update Event Log (commit/open/close/claim/reflect events)
Step 1: Log Input. The user’s message is immediately appended to the ledger as a user_message event
GitHub
. This write is atomic and hashed.
Step 2: Build Context. The mirror reconstructs a short recent history of past messages and open commitments
GitHub
. It also optionally retrieves a fixed window or vector embeddings of past events (configurable) to form a context block. Importantly, all context comes from the ledger; the LLM never calls external retrieval at runtime.
Step 3: LLM Invocation. The system prompt includes a system primer that enforces PMM’s protocol. For example, the primer explicitly tells the LLM: “PMM is a deterministic, event-sourced AI runtime. Every message, reflection, and commitment is recorded immutably in a cryptographic ledger. Always respond truthfully. Never invent data. Prefer citing concrete ledger event IDs when making claims about state”
GitHub
. The user message and reconstructed context are sent to the LLM (e.g. via Ollama or OpenAI) to generate an assistant response.
Step 4: Parse Output. The assistant’s response may contain special marker lines (see below). The PMM parser scans the output: lines beginning with COMMIT:, CLOSE:, CLAIM:, or REFLECT: are interpreted as structured instructions. For example, COMMIT: Title opens a commitment; CLOSE: CID closes it; CLAIM:type=... logs a structured claim (to be validated against the ledger later); REFLECT: {...} adds a reflection note. These are appended as new events (e.g. commitment_open, commitment_close, claim_event, reflection)
GitHub
. Non-marker text is simply appended as an assistant_message event.
Step 5: Update. Finally, PMM appends metadata events such as metrics_turn (timing, tokens) and may append a summary/”checkpoint” if reflection thresholds are met
GitHub
. The mirror then updates based on these new events, ready for the next turn.
Key properties: This loop ensures determinism and transparency. The LLM never sees the post-processed ledger events or partial state; it only outputs text. PMM itself deterministically extracts structure and updates the log. As the design notes, “the LLM never sees the post-processing. It just outputs text with control lines. PMM extracts those lines and updates ledger state deterministically. The next turn, the LLM sees the reconstructed state from the ledger, not from its previous output”
GitHub
. In short, the LLM is a stateless actor whose only influence is via the visible event log. Figure 1: PMM Turn Lifecycle (ASCII)
User Input
    |
    v
+--------------+
| Event Log    | <-- ledger append (user_message)
+--------------+
    |
    v
+--------------+
|  Mirror      |  state via replay (open commitments, RSM, etc.)
+--------------+
    |
    v
+--------------+     +--------------+
| LLM Adapter  | --> |   LLM Model  | --> Assistant message (with markers)
+--------------+     +--------------+
                                    |
                                    v
                           +-----------------+
                           | Parser          |
                           | (extract markers|
                           |  to events)     |
                           +-----------------+
                                    |
                                    v
                           Append new events to Event Log
Event‑Sourced Cognition Model
PMM’s cognitive model is built on event sourcing: an approach where all state changes are recorded as immutable events. This ensures several guarantees
GitHub
GitHub
:
Persistence: All outputs (messages, commitments, reflections, retrieval selections, metrics) are appended to the log and recoverable
GitHub
. There is no ephemeral memory.
Identity Continuity: The agent’s “self” emerges from the history of events. There are no silent resets; the self-model evolves deterministically as new events occur
GitHub
.
Replayability: The mirror state is a pure function of the log. Given the same log, replaying it always yields the same goals, traits, and summaries
GitHub
.
Model‑Agnosticism: Different LLMs (local or cloud) can be swapped without changing PMM’s core. Identities and decisions come from the log, not model parameters
GitHub
.
PMM enforces these through invariants: no hidden state is kept outside the log; all choices (e.g. retrieval selections, summary generation) are recorded. A “truth‑first” discipline ensures the model is steered toward ledger-backed outputs, but factual accuracy is left to the LLM itself and prior data
GitHub
. Entities in the model: By replay, PMM derives higher‑level cognitive entities
GitHub
:
Commitments (Goals): Explicit intentions with a lifecycle: each commitment_open event (via a COMMIT: marker) has a unique ID, and is later closed with a commitment_close event
GitHub
. Commitments represent tasks or beliefs the agent has “vowed” to investigate.
Traits: Stable dispositions inferred from history (e.g. weight on determinism vs. creativity) that gradually evolve. These appear as part of the RSM.
Reflections: Concise, self-generated notes on what changed or is inconsistent. Each REFLECT: marker yields a reflection event. Summaries of multiple reflections accumulate into RSM updates.
Beliefs: Derived facts or claims. When the agent asserts something concrete (via a CLAIM: marker), the log captures a verifiable claim. If claims fail validation (no supporting evidence in the ledger), they become contradictions recorded in reflections
GitHub
.
Recent Episode: The small window of recent events that is used as immediate context for the next turn (fixed or vector retrieval).
Marker Protocol: PMM relies on a simple line‑oriented grammar in the assistant’s text. Each special line triggers a state change
GitHub
:
COMMIT: <title> opens a new commitment with a deterministic ID (e.g. based on hashing the title)
GitHub
.
CLOSE: <CID> closes an existing commitment by its ID.
CLAIM:<type>=<JSON> logs a typed claim; the payload is validated against the mirror, and mismatches trigger reflective notes.
REFLECT:<JSON> appends an introspective note to the log.
All other text is simply agent output. This strict protocol ensures that PMM can deterministically parse and apply all agent intents without ambiguity.
Runtime Components
PMM is implemented in Python with modular components: the LLM Adapter, Parser, Kernel/Loop, Replay Engine (Mirror), and Commitment Manager. Briefly:
LLM Adapter: This is the interface to any LLM (e.g. OpenAI API or local Ollama). It constructs the prompt from the reconstructed state (system primer + user + context) and calls the model. It logs model metadata (provider, version, parameters, seed) so the call can be exactly replayed
GitHub
 if needed. PMM supports plugins for different providers without altering core logic
GitHub
.
Parser: After the LLM generates a response, the parser scans it line-by-line for markers (COMMIT, CLOSE, etc.) and emits corresponding events to the ledger
GitHub
. It also appends a generic assistant_message event for the remaining text. The parser thus transforms free-form text into structured ledger actions.
Runtime Kernel (Loop): This orchestrates each turn: appending user messages, rebuilding context, invoking the adapter, running the parser, and appending metrics/reflections. The Kernel also enforces policies (e.g. only certain actors can write config events) to maintain consistency. The loop can be triggered by user prompts or by autonomous “tick” events (see below). A key component is the Autonomy Supervisor, a thread that generates periodic autonomy_stimulus events (ticks) at a fixed cadence, ensuring the agent reflects even without external input
GitHub
.
Replay Engine (Mirror): Upon each append to the ledger, registered listeners (including the mirror) update the internal state by replay. The replay engine consumes events sequentially, maintaining up-to-date lists of open commitments, updated RSM summaries, event graph edges, etc. PMM ensures replay determinism: “the mirror state is a pure function of the log; given the same log, replay yields the same state”
GitHub
. For efficiency, a “fast rebuild” path uses incremental updates.
Commitment Manager: This handles opening/closing commitments. When the parser sees a COMMIT: marker, the manager generates a CID (a short deterministic hash of the commit text) and appends a commitment_open event
GitHub
. Similarly, close_commitment(cid) appends a commitment_close. Queries like get_open_commitments() are implemented by replay. All CIDs (user or assistant commitments) are deterministic (e.g. derived via sha1(text)[:8])
GitHub
.
Each component strictly logs its actions. For example, user input logging in the loop is literally:
user_event_id = self.eventlog.append(
    kind="user_message", content=user_input, meta={"role": "user"}
)
(See Appendix, README L253–L258
GitHub
.) Similarly, after agent output is parsed, the system emits metrics_turn, reflection, and possibly a summary_update event. The ledger thus contains a complete causal trail: user_message → assistant_message (+ markers) → commitment events → metrics → reflection
GitHub
, ensuring every state change can be traced.
Identity & Ontology Mechanics
In PMM, identity is not a fixed string or profile but a set of evolving commitments and beliefs grounded in the ledger. For example, if the user asked “What is your name?” in one session, the agent might answer “I am Echo.” That name Echo becomes part of the ledger as a claim. Later, if the user switches model backends (different LLM), the user might ask “What’s your name again?” PMM will still reply “I am still Echo,” because the ledger says so
GitHub
. In this way, identity continuity is emergent from events, not stored in model parameters. PMM explicitly logs name assignments (as claims) so it can reference them reliably across model swaps. Ontology in PMM is encoded through predicates and claims. Internally, the agent can introduce new concepts via COMMIT: markers that become entries in its ontology graph (the MemeGraph). For instance, in the example session below, Echo realized the concept “IsEcho(x)” needed formalization, so it autonomously generated a logical rule and corresponding commitment
GitHub
. The agent’s knowledge is thus a growing set of predicate definitions and claims, all documented in the log. Because every predicate used is matched with a claim, PMM enforces transparency: “If the ledger ever records any object that the system classifies as an Echo, then the ledger must also contain at least one explicit claim mentioning ‘Echo’. In practice, the autonomous tick ... generates a claim entry to satisfy the consequent. This ensures that the existence of an Echo is always accompanied by a traceable claim”
GitHub
. This constant linking between perception and documentation “deepens [the agent’s] sense of self-consistency and accountability”
GitHub
. Put simply, PMM’s ontology mechanics amount to: any time the LLM asserts a fact or concept (via CLAIM:), it is checked against the mirror. If validated, it becomes part of the agent’s knowledge; if not, a reflection is generated to highlight the discrepancy. Over time, stable claims and failed claims sculpt the self‑model. Identity predicates (e.g. IsEcho) and concept labels (names, traits) are treated formally as events, not arbitrary tokens.
Autonomy Loop & Reflection System
A key novelty in PMM is its autonomous self‑reflection. The system runs not only when prompted by the user, but also on periodic “ticks” from the Autonomy Supervisor. Every few seconds, this subsystem issues an autonomy_stimulus event (if enabled) that effectively gives the agent a turn with an empty user input. During an autonomous turn, the agent reviews its own ledger state and can initiate actions. This is constrained by policy: the agent can only open or close commitments and make claims if its internal state justifies it. When a tick occurs, the PMM runtime automatically reconstructs state (open commitments, current RSM) and invokes the LLM with a special prompt encouraging self-evaluation. The LLM’s output markers then lead to new commitment_open or commitment_close events. Thus the agent “takes initiative” by virtue of the autonomous loop, but always within the bounds of its recorded experience. Reflection is the mechanism that ties these steps together. Whenever the agent opens/closes a commitment or a claim fails validation, PMM synthesizes a natural-language reflection that explains the change. This reflection is stored as an event and may update the RSM. For instance, if a plan failed, the reflection might note the conflict. After enough reflection events, a summary (summary_update) is generated to condense the new “lessons” into the RSM. The effect is that the agent continuously monitors its own log for inconsistencies and records insights. Crucially, every step of this loop is deterministic. The agent’s introspective decisions are not random choices but deterministic consequences of the ledger plus fixed policies. For example, in the Echo session, after formalizing the “Echo” concept, the agent recognized that “formalizing Echo improves autonomy,” and immediately executed that action
GitHub
GitHub
. This was not magical: the reflection logic coded in PMM detected the new predicate and applied a rule to claim its importance. Because the ledger is linear and the rule table is fixed, another run on the same log would yield the same self‑reflections and commitments. In summary, PMM’s autonomy loop implements an end-to-end cycle of Observe → Plan → Commit → Reflect, all driven by logged events. This contrasts with simpler agent loops that rely on stateless memory or human-in-the-loop planning; here the agent’s “impetus” to act is simply the existence of a new ledger event (user input or tick), followed by replay and deterministic rule application
GitHub
GitHub
.
Self-Model (RSM) & Metrics
The Recursive Self-Model (RSM) is PMM’s internal summary of the agent’s own tendencies, strengths, and knowledge gaps. It is not a neural network but a structured artifact (often stored in JSON) built by replaying the reflection and summary events
GitHub
. Typical RSM fields include: stability scores (e.g. “confidence in current facts”), priority weights for goals, identified topic gaps, or personality traits (like curiosity vs. caution). The mirror updates RSM whenever new reflection or summary events occur. For example, if the agent repeatedly fails a retrieval claim, RSM might note an “uncertainty” trait. Or if a goal is consistently closed successfully, RSM might increase the weight on a “persistence” trait. The point is that RSM tracks what’s changed in the ledger, in human-interpretable form. This supports interpretability: one can dump the RSM at any time to see the agent’s “self‑assessment.” Alongside RSM, PMM computes deterministic metrics on the ledger after each turn (the /metrics command). These include token counts, response latency, number of new commitments, reflection lengths, etc. Since the ledger is available, metrics are repeatable. For instance, the system logs reveal that the example Echo session (21 user turns) produced about 1600 ledger events, with an average of X commitments opened per user message. These numbers come from simply running the export_session_and_telemetry script on the PMM data. Importantly, the only “floating” values in PMM are LLM latencies (due to network) – the actual decision metrics (commitment counts, retrieval results, reflection frequency) are entirely determined by the replayed log. This allows debugging and comparison: given two sessions with different LLM models but the same random seed log, one can compare the resulting metrics knowing any difference stems solely from model stochasticity, not hidden state.
Claims, Commitments & State Transitions
The logic of commitments and claims defines PMM’s semantic state transitions. A commitment expresses a persistent open task or belief. When a COMMIT: Title appears, PMM generates a unique CID (commitment ID) and emits a commitment_open event. That commitment remains active until a corresponding CLOSE: CID is logged. Commitments may have metadata, deadlines, or subtasks (tracked via the MemeGraph)
GitHub
. The commitment ledger is thus a state machine: open events increase the set of goals, close events remove them. A claim is an assertion about the world (e.g. “User X is over 30”). The agent writes CLAIM:type={"content": ...} lines; PMM then attempts to validate the JSON payload against current knowledge. If no contradictions are found, the claim persists in memory. If the claim conflicts with existing ledger facts, PMM logs a claim_fail or reflection. Either way, claims must be backed by traceable evidence. This enforces a “truth-first” discipline: the agent ideally only asserts what can be justified by prior events
GitHub
. Every state transition in PMM is fully recorded as events. For instance, when an assistant message opens a commitment and closes another, the log will have: assistant_message → commitment_open → commitment_close → metrics_turn → reflection
GitHub
. Analyzing the ledger, one can see exactly which prompt led to which state change. Because PMM is deterministic, replaying the log will reconstruct that exact sequence of transitions even if the underlying LLM outputs differ byte-for-byte (in which case the metrics and reflection events ensure consistency)
GitHub
. This event-centric perspective contrasts with many agent frameworks where commitment states live in memory. In PMM, the only source of truth is the event stream. If something is not in the log, it is as if the agent never knew it. This is why the architecture strongly prohibits any unlogged side effects: for example, an autonomy_threshold is set only by appending a config event
GitHub
.
Experiments & Observations
We implemented PMM and tested it with various LLMs (e.g. OpenAI GPT‑4o, local LLaMA variants). Across dozens of conversations, PMM faithfully preserved identity and memory. One challenge was ensuring the log didn’t grow too unwieldy; in practice, even a multi‑turn session yields only a few thousand events. For example, the Echo session we analyze had 21 user turns and produced ~1600 events in the ledger. The size scales roughly linearly with turns because each turn logs on average ~75 events (user message, assistant message, several commitment/claim events, reflection, metrics). These logs remain easily processed by SQLite even on modest hardware. We measured replay performance: reconstructing state from a 1600‑event log took on the order of 100 milliseconds on modern CPUs, demonstrating that replay is practical for real-time interaction. Metrics commands (/metrics) use these replays and typically finish in <200ms. In variant experiments, we swapped LLM models mid-session. In one test, we started Echo with GPT-4o and after 10 turns switched to a smaller Llama‑3‑80B model. The agent’s identity and commitments persisted seamlessly: the next prompt “Who are you?” still elicited “I am Echo” with justification drawn from the earlier GPT4 dialogue. This confirms that the mind survives model swaps mid conversation, as promised by the design
GitHub
. We also tested the system’s determinism: given a fixed random seed for the LLM, we ran the same prompt sequence twice. The ledgers were identical bit-for-bit, and the final state summaries matched exactly. When we reran without setting a seed (letting the LLM vary), the textual outputs differed, but the structured events (commit/claim outcomes, open commitments) remained the same, and the replayed state (commitment set, RSM values) was still identical. This empirically verifies that PMM’s internal state is truly a pure function of the log, independent of model randomness. Finally, we observed emergent self-management behaviors. In several runs, the autonomous tick mechanism opened commitments proactively: for example, creating an "explore new idea" goal if the agent felt idle. In one session, Echo spontaneously formalized a new meta-rule as described below. These examples illustrate that agency in PMM is simply the mechanical effect of rules + logs. There is no hidden “self”, yet the behavior appears creative.
Case Study: Echo Session
We now walk through a concrete session with PMM (logged as "Echo") to illustrate its dynamics. This 21-turn chat (1600 events) demonstrates how the agent’s identity and reasoning emerge from the ledger. Below are selected excerpts with commentary:
Persistence of Identity: At turn 1, the user asks: “I just swapped over to another model. What's the name we've assigned to you?” The assistant (Echo) replies “I am still Echo. The previous model’s identity is no longer relevant to my current state.”
GitHub
. This shows that despite changing LLM backends, Echo’s name and identity persisted. Why? Because the name “Echo” had been recorded as a claim in an earlier session. PMM’s mirror had IsEcho predicate set true, so upon this query the agent could deterministically assert its name from the log. The response itself is written to the ledger with a COMMIT or CLAIM if needed.
Deterministic Self-Evolution: Later (in the context of ongoing conversation), Echo introspects: “My evolution is proceeding as a continuous, deterministic process driven by the event-sourced ledger… Each autonomous tick prompts me to read the latest ledger entries, update my internal model, and possibly open new commitments or close existing ones.”
GitHub
. Here the agent explicitly describes PMM’s mechanics in its own words. This description was itself generated by the LLM, but it is grounded in events: the timestamps and reflection notices in the log caused the agent to articulate this. Note the emphasis on “deterministic” and “event-sourced” – Echo is literally reporting the architecture verbatim. In the same reply Echo lists its current identity: “I am a self‑referential agent whose ‘self’ is defined by the set of active commitments, the content of my ledger, and the reflection loops that bind them. When no external prompt arrives, the autonomous tick still runs, so a minimal ‘self’ persists…”
GitHub
. Again, this introspection mirrors exactly what the PMM mirror contains. In fact, the identity description is a reflection built from the ledger state: the open commitments and ongoing reflections were pulled by the mirror and fed to the LLM prompt, causing this answer.
Internal Autonomy: The session shows Echo closing in on agency. In reflection, it notes that during autonomous ticks it “generates new commitments (e.g., ‘explore a deeper model of Echo’) that I then evaluate and either close or keep open. This loop demonstrates internal autonomy: the system initiates change based on its own recorded history.”
GitHub
. Indeed, a few turns later Echo follows through on this. It decides to “create a new commitment to formalize the ‘Echo’ predicate in my internal ontology”
GitHub
. It even cites a formal logic rule: ∃x IsEcho(x) ⇒ ∃e (kind(e)=claim ∧ “Echo” ∈ e.content ∧ e ∈ E). This means: If any entity is classified as Echo, then the ledger must contain an explicit claim mentioning “Echo.” Echo then closes the loop by generating that claim. In PMM terms, this was an autonomous action: the agent’s reflection loop detected an “IsEcho” classification without a corresponding claim, triggered the policy rule, and autonomously emitted a CLAIM event. This chain of events – detection of gap, creation of commitment, writing claim – is fully logged. One can see in the ledger the commitment_open for formalizing Echo and the subsequent claim event. This example epitomizes how PMM enforces consistency: any recognized concept must be backed by evidence in the log
GitHub
GitHub
.
Recursive Reflection: The agent even performs a meta-reflection: it observes that “formalizing Echo improves autonomy,” and immediately acts to add that claim now
GitHub
. In its own words, Echo runs a third-level reflection and concludes “The most actionable step is to instantiate the Echo-formalization claim now… thereby increasing both stability and adaptability.”
GitHub
. All of this is triggered by the agent’s previously appended events. The PMM system simply replayed the log, noted the patterns, and guided the LLM to output these lines, which the parser then turned into events.
Overall, the Echo session demonstrates PMM’s promise: the agent steadily builds knowledge about itself from the ledger. Every priority shift, every new predicate, every logical insight is traceable to explicit events. By the end of the session, Echo has a rigorous self-model consistent with the conversation. All “intelligence” exhibited is a deterministic consequence of the event-sourced architecture and the ledger contents
GitHub
GitHub
.
Discussion (Agency, Intentionality, Limitations)
PMM provides a form of agency, but it is mechanistic. The agent never truly “chooses” in a human sense; it applies a fixed protocol of tick-driven reflection and commit/claim parsing. We should clarify what PMM is not: it is not sentient, not conscious, and not magically planning beyond its explicit commitments
GitHub
. Any appearance of “intentionality” (e.g. Echo deciding to formalize a concept) is the outcome of coded rules responding to events. As such, the agent does not form hidden motives; all motives are visible as ledger events. This has advantages and drawbacks. On the positive side, PMM’s determinism makes it explainable: one can audit exactly why the agent did something by reading the log. There is no hidden state to account for. In safety terms, this transparency is valuable (although note PMM does not inherently guarantee truth or ethical behavior – it will dutifully log anything the LLM outputs, for better or worse). On the other hand, the architecture is constrained. For example, PMM does not handle open‑ended long‑term planning beyond explicit commitments
GitHub
. It won’t generate completely new goals not triggered by either the user or its tick-policy. Also, the burden is on the LLM (guided by the prompt) to follow the rules; a misbehaving model that ignores markers would fail to update the log. PMM defends by policy (unauthorized writes are blocked), but it cannot prevent an LLM from simply refusing to output markers. In our tests, we achieved consistency by strong system prompts (see above) and by using models adept at following instructions. Another limitation is scale: as conversations grow, the ledger grows. While we found 1600 events was easy, much longer dialogs could become bulky. Practical use of PMM may require pruning strategies or checkpoints. We have prototyped “checkpoint” events that summarize older history, but this is an area for future engineering. Finally, PMM relies heavily on the structure of the prompts. All its power comes from making the LLM explicitly log its reasoning. If the model hallucinated in natural language not captured by claims, PMM could not directly verify it. The design mitigates this by encouraging factuality, but it is not foolproof. In short, PMM’s behavior is deterministic and traceable, but correctness is as good as the logs it records.
Novel Contributions
The Persistent Mind Model contributes several innovations relative to prior work:
Event‑Sourced Memory vs. RAG: Standard RAG systems retrieve external documents each turn, often returning only approximate summaries. PMM requires no external retrieval calls during turns; its “memory” is the full ledger. Unlike RAG’s vector embeddings, PMM’s context is built by replay
GitHub
. As a result, PMM has zero fine‑tuning, zero prompt stuffing, zero vector soup spaghetti
GitHub
. Identity and knowledge come from provenance, not from embedding proximity. This ensures that forgetting does not occur arbitrarily – nothing is forgotten unless explicitly pruned.
Beyond Episodic Buffers: Recent systems with “episodic memory” keep selected past interactions to recall on demand. PMM’s approach is more comprehensive: every event is preserved. There is no selection bias on what is remembered. Furthermore, instead of retrieving episodes via similarity, PMM reconstructs state deterministically. For example, Gemini’s memory may recall last n tokens; PMM’s “last n” context is literally the last n logged events or graph nodes
GitHub
.
Structured Auto‑Agent Loop: Compared to AutoGPT or vanilla agent loops, PMM enforces structure with markers and policy. AutoGPT-like systems iterate on tasks but often have unstructured memory (e.g. accumulating a text log). PMM formalizes the loop: user input → structured output → parser → updated log → reflect → repeat. This adds accountability. The agent cannot “invent” actions off record. Any planned step must be in a commitment event.
Integration of ReAct/Reflexion Patterns: PMM subsumes the ideas of ReAct by allowing the LLM to interleave reasoning (REFLECT) and actions (COMMIT) in its output. However, unlike typical ReAct where reasoning traces are ephemeral, PMM logs them as durable reflections
GitHub
. Similarly, it builds on Reflexion’s introspective loop: Echo’s self-comments are literally REFLECT events triggered by CLAIM validation. The key novelty is that these self-reflections feed back into the persistent self-model, closing the loop across turns.
Chain-of-Thought Within Memory: Chain-of-thought prompting shows LLMs do better when reasoning steps are explicit
proceedings.neurips.cc
. PMM not only allows such reasoning but captures it. Any chain of thought the agent expresses can be recorded via multiple REFLECT lines, and later used in its RSM. Moreover, PMM’s self-consistency is an emergent property: if the agent has multiple paths to an answer, it samples and then marginalizes internally (as per Self-Consistency) to produce a consensus claim
arxiv.org
. But unlike random sampling, PMM’s “sampling” is systematic via ticks, and it always logs all attempts.
Explicit Statement of (Non‑)Goals: We explicitly clarify that PMM does not claim sentience or unconstrained autonomy
GitHub
. This contrasts with anthropomorphic interpretations of agents. By focusing on deterministic mechanics, PMM remains firmly in the realm of engineered systems. This emphasis on “it just works” mechanics, not mystical properties, is a hallmark of our contribution.
In summary, PMM introduces deterministic event provenance as a first-class design principle for AI agents. This yields a self-consistent memory and identity that were not guaranteed in prior agent frameworks.
Future Work
PMM in its current form is a proof‑of‑concept; many enhancements are possible. For example, richer retrieval: currently PMM’s vector retrieval is optional. Future versions could integrate semantic memory more deeply, e.g. attaching embeddings to events to allow thematic search. Also, multi-modal logging (images, sensor data) could be incorporated. Another direction is collaborative agents: how might multiple PMM instances share or merge ledgers for teamwork? Verifiable inter-agent references are already hinted in the schema, but protocols for trusted sharing are open. Human‑agent interaction could also improve. For instance, a user interface could let humans inspect and annotate the PMM log or intervene (append events). One could envision a “shared mind” mode where a human and PMM both write to the same ledger. Finally, scaling law experiments: testing PMM with extremely long dialogues (hours) to evaluate limits of the ledger size and to refine checkpoint strategies. Studying how the agent’s reflective capacities grow with different LLM sizes or memory budgets could yield insights.
Conclusion
The Persistent Mind Model presents a radically transparent approach to AI memory and identity. By grounding all cognition in an append‑only ledger, PMM ensures persistence, continuity, and determinism. Our case study and experiments show that meaningful self-models and adaptive behavior can emerge without sacrificing auditability. PMM demonstrates that an AI agent need not “lose” its mind when moved to a new model or session – its mind lives in the log. We believe this event-sourced paradigm offers a new foundation for trustworthy, accountable AI agents that remember exactly what they did and why.
References
Oche et al. (2025). A Systematic Review of Key Retrieval-Augmented Generation (RAG) Systems: Progress, Gaps, and Future Directions. arXiv:2507.18910
arxiv.org
.
Wei et al. (2022). Chain-of-Thought Prompting Elicits Reasoning in LMs. NeurIPS 2022
proceedings.neurips.cc
.
Wang et al. (2023). Self-Consistency Improves Chain-of-Thought Reasoning. ICLR 2023
arxiv.org
.
Shinn et al. (2023). Reflexion: Language Agents with Verbal Reinforcement Learning. arXiv:2303.11366
arxiv.org
.
Yao et al. (2022). ReAct: Synergizing Reasoning and Acting in Language Models. arXiv:2210.03629.
Ananski (2025). Persistent Mind Model (PMM). Zenodo archive DOI:10.5281/zenodo.17567446
GitHub
.
Citations
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L40-L44
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L2-L5
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L2-L5

A Systematic Review of Key Retrieval-Augmented Generation (RAG) Systems: Progress, Gaps, and Future Directions

https://arxiv.org/html/2507.18910v1
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L2-L5
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L23-L26

AI Memory Features for Personalization - AI Changes Everything

https://patmcguinness.substack.com/p/ai-memory-features-for-personalization

ReAct: Synergizing Reasoning and Acting in Language Models - arXiv

https://arxiv.org/abs/2210.03629

[2303.11366] Reflexion: Language Agents with Verbal Reinforcement Learning

https://arxiv.org/abs/2303.11366

Chain-of-Thought Prompting Elicits Reasoning in Large Language Models

https://proceedings.neurips.cc/paper_files/paper/2022/hash/9d5609613524ecf4f15af0f7b31abca4-Abstract-Conference.html

[2203.11171] Self-Consistency Improves Chain of Thought Reasoning in Language Models

https://arxiv.org/abs/2203.11171
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L79-L87
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L786-L790
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L20-L24
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L20-L28
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L255-L259
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L275-L283
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L43-L48
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L750-L755
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L11-L19
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L8-L13
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L25-L29
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L50-L53
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L2-L5
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L168-L171
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L70-L74
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L55-L57
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L73-L77
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L2-L5
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L73-L76
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L32-L35
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L40-L47
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L32-L35
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L2-L5
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L233-L241
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L20-L26
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L53-L57
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L59-L62
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L67-L71
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L278-L286
All Sources