The Persistent Mind Model (PMM): A Deterministic, Event-Sourced Architecture for Long-Term AI Memory
Abstract
We introduce the Persistent Mind Model (PMM), a novel cognitive architecture for large language agents that treats the agent’s “mind” as an append-only event ledger, enabling persistent memory, identity, and auditability. PMM records every user interaction, system response, internal reflection, and commitment as immutable events in a timestamped, hash-chained log. A deterministic replay engine reconstructs the agent’s state (beliefs, goals, self-model) purely from the ledger, ensuring identity continuity across sessions and even after model swaps
GitHub
GitHub
. PMM enforces a truth-first discipline by checking all planned assertions against the ledger, preventing ungrounded “hallucinations” and making reasoning explicitly traceable
GitHub
GitHub
. We describe PMM’s architecture and runtime components (LLM adapters, output parser, replay mirror, commitment manager, autonomy kernel, etc.), illustrate how an internal Recursive Self-Model (RSM) emerges from event history, and detail the handling of explicit claims and commitments. In empirical tests (notably a 21-turn “Echo” session with ~1600 logged events), PMM demonstrates deterministic, self-consistent behavior: e.g., after a user swaps the model mid-conversation, the agent reliably answers “I am still Echo” rather than “forgetting” its identity
GitHub
. We compare PMM to existing memory and agent paradigms (retrieval-augmented generation, episodic buffers, AutoGPT-style loops, ReAct/Reflexion frameworks, chain-of-thought, etc.), highlighting that PMM’s novel contribution is the event-sourced ledger itself – a fully replayable, theory-of-mind substrate that gives rise to persistent agency. PMM is not a metaphysical or anthropomorphic claim about consciousness, but a practical software design that achieves deterministic, forensic AI behavior as confirmed by logged data
GitHub
GitHub
. We present metrics and a case study to characterize PMM’s behavior, discuss implications for agent autonomy and limitations, and outline future work on scaling and applying event-sourced cognition to multi-agent and real-world domains.
Introduction
Large language model (LLM)–based agents today suffer from transient memory and untraceable reasoning. Conventional chatbots “forget” past interactions between runs, have no persistent state, and may hallucinate ungrounded claims with no audit trail. Users cannot replay an agent’s chain of reasoning or verify what it “believed” at a prior time
GitHub
. To address these gaps, we propose the Persistent Mind Model (PMM), a deterministic architecture that records every decision and inference in an append-only ledger. In PMM, an agent’s identity and knowledge emerge from the log itself, not from hidden neural parameters or black-box prompts
GitHub
GitHub
. For example, when an agent is asked mid-session “What name have we assigned to you?”, PMM’s log-based self-model can determine and answer “I am still Echo”, even if the underlying LLM was swapped — it simply looks up the prior identity from the event history
GitHub
. PMM’s core idea is that cognition is computation over an immutable event history. The system enforces that every output (user messages, assistant responses, internal reflections, goals, etc.) is logged with a hash-chained timestamp. A runtime mirror component replays this log to derive the agent’s current beliefs, open goals, and sense of self
GitHub
GitHub
. Crucially, this design makes all reasoning auditable and reproducible: given the same ledger, PMM’s replay yields identical state and decisions
GitHub
GitHub
. In contrast to probabilistic chains-of-thought, PMM’s reasoning steps are deterministic consequences of the recorded events. This yields key benefits: persistent memory without growing model parameters or expensive retraining, automatic truth-checking via consistency with past events, and built-in support for agent introspection and reflexivity. This paper presents the PMM in full detail. We first situate PMM relative to prior work on memory and agent loops. We then give an architecture overview, followed by a breakdown of PMM’s components: the event-sourced ledger, the replay Mirror, the Recursive Self-Model (RSM), the autonomy/reflection loop, and the commitment/claim mechanism. We describe how PMM’s behavior (agency, commitments, goal evolution) is a deterministic outcome of its event-driven architecture, as confirmed by ledger logs. An empirical case study (“Echo session”) demonstrates these properties in a real chat: the ledger (≈1600 events over 21 turns) shows how identity, metrics, and commitments evolved step by step. Finally, we discuss implications for intentionality and limitations, outline PMM’s novel contributions, and suggest future work. Throughout, we avoid any anthropomorphic or metaphysical claims: PMM is a software framework, not a theory of consciousness. Its “self” is merely the pattern of logged commitments and reflections.
Background & Related Work
Modern LLM agents have incorporated various memory and reasoning techniques, but none provide the fully persistent, auditable memory that PMM does. Standard Retrieval-Augmented Generation (RAG) systems add external memory by storing documents or past text in a vector database
arxiv.org
. While RAG can improve factuality, it typically uses non-deterministic retrieval (nearest-neighbor search) and lacks a causal trace of why a particular piece of knowledge was used
GitHub
arxiv.org
. Vector memories also must be separately managed and do not inherently record agent introspection or goals. PMM, by contrast, stores all relevant data (including internal reasoning) in a structured log, with deterministic replay ensuring the same context is recovered every time
GitHub
GitHub
. Other approaches aim to give LLMs short-term memory. Some commercial models (e.g. Google Gemini’s memory feature) maintain a session history across interactions, but these are typically limited in scope and not exposed to the user. Likewise, episodic buffer techniques (as in human cognitive architectures or agent frameworks) focus on recent context, not a verifiable long-term record. Without strict logging, such methods cannot guarantee consistency over time. In contrast, PMM’s event log is permanent and content-addressable, so every inference is reproducible and explainable. There has also been work on autonomous agent loops and reflection: for example, AutoGPT-style systems or frameworks like ReAct
arxiv.org
arxiv.org
. These systems repeatedly call an LLM to plan and act, sometimes incorporating feedback. However, most lack any formal persistent memory: they rely on the LLM’s hidden state or carryover context, and usually do not record internal steps systematically. ReAct (“Reasoning+Action”) trains LLMs to interleave reasoning traces and actions
arxiv.org
arxiv.org
; Reflexion agents
arxiv.org
 explicitly reflect on trial outcomes to improve, but only store an episodic buffer of recent reflections. None of these build an immutable history of every step. PMM’s novelty is to make the history itself the agent’s memory, unlocking deterministic autonomy and auditability. Chain-of-thought prompting
arxiv.org
 and related techniques (self-consistency, etc.) demonstrate that encouraging LLMs to break problems into steps can improve performance. These methods coax an LLM to internally reason, but they do not externalize or persist that reasoning beyond the immediate generation. By contrast, PMM externalizes each reasoning step as a ledger event (e.g. COMMIT, CLAIM, REFLECT entries), preserving them for future review. Thus PMM could be paired with chain-of-thought style reasoning while still logging the outcome. In summary, prior methods either extend memory via vector retrieval or leverage ad-hoc prompting, but they lack PMM’s combination of persistent external memory, deterministic replay, and structured self-reflection. Table 1 (from our technical notes) contrasts PMM with RAG and prompt-engineering approaches, highlighting PMM’s portability and auditability
GitHub
GitHub
.
Architecture Overview
At the highest level, PMM views the agent’s mind as an event-sourced ledger
GitHub
. The architecture comprises the following key layers (see Figure 1):
User Input → Ledger Event (immutable)
         ↓
    Replay State (Mirror)
         ↓
   LLM Inference (with short context)
         ↓
Assistant Output → Ledger Event
         ↓
    Self-Model Update (RSM metrics)
         ↓
      [repeat]
Figure 1. PMM transaction flow (simplified). Each user message and assistant reply is written to the append-only ledger. The Mirror replays the log to build current state (open commitments, traits, RSM snapshot). The LLM is then invoked with a compact prompt (recent tail + state). The assistant’s response (including any structured markers like COMMIT:) is parsed and appended as new events. Finally, the Recursive Self-Model (RSM) updates its metrics based on the expanded ledger
GitHub
GitHub
. PMM’s event log is a SQLite database of JSON events
GitHub
. Each event has a kind (e.g. user_message, assistant_message, commitment_open, reflection, etc.), content, timestamp, and a hash linking it to the previous event for integrity
GitHub
. The Mirror component performs state reconstruction by replaying all or a window of events: it computes open/closed commitments, known facts, and the RSM (beliefs and traits inferred from history)
GitHub
GitHub
. Because the ledger is immutable and ordered, the Mirror’s state is a pure function of the log. This guarantees full reproducibility: the same event sequence always yields the same internal state
GitHub
. On each turn, the Runtime Loop proceeds as follows:
Input: The user’s message is immediately appended to the ledger (kind=user_message)
GitHub
.
Recall: The Mirror replays recent events to extract: a fixed-length tail of past dialogue, the current set of open commitments/goals, the RSM snapshot (e.g. past reflections, beliefs), and any graph-based context. Optionally, a vector retrieval step may pull relevant past events deterministically (or a fixed-window fallback). The result is a context block that is fed to the LLM.
Reflect: The LLM may be prompted to reason about the current goals, resolve contradictions, or plan next steps. In practice, PMM uses an iterative reflect+refine mechanism: the LLM is allowed to generate output containing special markers (see below) that express its planned commitments, claims, or reflections.
Consolidate: Before finalizing, the system checks any tentative outputs (claims, closing commitments) against the replayed state for consistency. Contradictions trigger explicit corrections in the response.
Commit: The assistant’s message is appended to the ledger (kind=assistant_message). The output parser extracts structured markers such as COMMIT: <title>, CLOSE: <CID>, CLAIM:<type>=<json>, and REFLECT:<json>
GitHub
. Each marker generates corresponding events: commitment_open, commitment_close, claim, reflection with unique IDs. This updates the ledger of commitments and knowledge.
Respond: The user sees the assistant’s output text (without internal markers).
Update: After replying, PMM appends metrics_turn, reflection or summary_update events as needed (e.g. after several reflections) and recalculates RSM metrics (e.g. determinism, adaptability). Listeners update the in-memory Mirror and the causal MemeGraph of event links.
This lifecycle is illustrated in Figure 2. The key point is that every step is logged: not only the user and assistant messages, but also intermediate planning and updates. The only ephemeral data are scores and embeddings in memory; all substantive decisions become events.
Input → Recall → Reflect → Consolidate → Commit → Respond → Update
Figure 2. Turn lifecycle in PMM. Each phase reads from or writes to the ledger. The Reflect step may run iteratively with an autonomy kernel (see below). Commit markers in the response open/close commitments. The Update phase adds any reflection/summary events and updates RSM.
Event-Sourced Cognition Model
The cornerstone of PMM is event sourcing: the agent’s entire cognition is the result of a log of timestamped, immutable events
GitHub
. This has several consequences:
Persistence: Every decision output – including assistant messages, reflections, commitments, retrieved contexts, and computed summaries – is appended to the event log and can be replayed later
GitHub
. In practice, a PMM session lasting minutes can generate thousands of events, all stored on disk. The canonical store is just a standard SQLite database which can be backed up or shared.
Determinism: Because the log is the source of truth, PMM’s state is fully deterministic. The Mirror’s state (open commitments, inferred traits, RSM snapshot) is a pure function of the event sequence
GitHub
. Even LLM outputs can be made reproducible by logging the model version, prompts, and random seeds as event metadata
GitHub
. Thus a given session history will always produce the same agent response under identical conditions.
Auditability: An external auditor (or the system itself) can replay the entire ledger and retrace exactly why any statement was made
GitHub
. Unlike opaque neural memory, the provenance of every belief and action is recorded. For example, if the agent “knows” a fact, one can inspect which logged claim or statement introduced that fact. If a commitment was made, the entire argument around it is in the log. This fulfills a new standard of AI accountability: “the ledger is the mind”
GitHub
GitHub
.
No Hidden State: There are no secret variables. Intermediate LLM activations are not stored, only the final choices. Everything used in reasoning appears as a ledger entry. By design, PMM enforces that knowledge and intentions are evidence-backed: if a reflection or plan contradicts an earlier entry, PMM’s truth-first discipline requires reevaluation rather than blind overwrite
GitHub
. The architecture’s logical constraints ensure, for example, that contradictions in the log trigger explicit corrections, not silent erasures.
PMM is not a probabilistic black box. It is not making random “decisions” in an inscrutable way; its behavior is the logical outcome of processing the event history under fixed rules. As one of the reflected insights states: “Self-model enrichment does not alter deterministic computation but provides a traceable epistemic layer”
GitHub
. In other words, all adaptive behavior in PMM is a deterministic consequence of the event-sourced design, as the ledger events show.
Guarantees and Invariants
PMM enforces several strong invariants in its design
GitHub
：
No Hidden Memory: Durable decisions are captured as events; nothing is stored off-log.
Truth-First: Planning prompts and commit-check rules are deterministic; any statement that cannot be backed by the ledger is either flagged or revised.
Reconstructability: Any state or decision is explainable from the causal chain of events (the Event Graph).
Importantly, PMM also has clear non-goals. It does not claim sentience, deep learning of new parameters, or unconstrained autonomy beyond the logged commitments
GitHub
. In particular, it is not engaging in unconstrained world modeling: open-ended long-term planning happens only insofar as commitments are explicitly logged.
Runtime Components
PMM’s architecture is implemented with modular components, each interacting with the ledger:
LLM Adapters: PMM is model-agnostic: it supports multiple LLM backends (e.g. OpenAI, local Ollama models). The adapter handles API calls, streaming, and mapping responses to the PMM framework. Swapping models mid-session is seamless because the adapter simply logs the model identity and uses it for subsequent calls
GitHub
. All LLM calls are deterministic if their random seed is logged.
Output Parser: The assistant’s reply may include special marker lines that denote structure. The parser scans the text (line-by-line) for markers:
COMMIT: <title> opens a new commitment.
CLOSE: <CID> closes an existing commitment.
CLAIM:<type>=<json> records a structured claim of a given type.
REFLECT:<json> records a self-reflection note.
Each such marker generates corresponding events in the ledger: commitment_open, commitment_close, claim, reflection
GitHub
. For example, if the assistant outputs COMMIT: Explore alternate theory, the parser will deterministically create a commitment_open event with a new unique ID. Because the parser is deterministic and rule-based, the commitment IDs and content are reproducible.
Commitment Manager: This subsystem tracks active commitments (goals the agent intends to pursue) and closed commitments. When the parser opens or closes commitments, the Commitment Manager updates the ledger and internal state accordingly. Importantly, a closed commitment is never forgotten; the closure event remains in the log for audit. Commitments serve as explicit intentions that the agent will try to satisfy in future behavior
GitHub
GitHub
.
Mirror (Replay Engine): The Mirror continuously rebuilds state from the ledger. It listens to new events and updates an in-memory “snapshot” of the agent’s mind: the set of open commitments (goals), a MemeGraph of causal links between events (who replied to what, which claim belongs to which commitment, etc.), stable traits inferred over time, and the Recursive Self-Model (RSM) – a collection of internal metrics and summarized beliefs. The Mirror’s logic is purely functional: given an event log, it deterministically outputs the state. This is the core of PMM’s determinism guarantee
GitHub
.
Autonomy Kernel & Reflection: An Autonomy Supervisor thread emits periodic autonomy_stimulus events (determined by fixed time slots and hash IDs)
GitHub
. Each stimulus triggers an autonomous tick: the system replays the log, sees no user input has arrived, and invokes the LLM to reflect on current commitments and traits. During a tick, the LLM may generate new COMMIT, CLAIM, or REFLECT entries in its response without user prompt. For example, in Figure 2’s example, the autonomous tick caused the agent to formally encode the concept “Echo” by opening a commitment
GitHub
. Thus PMM can self-initiate planning: “internal autonomy” emerges purely from the logged history.
Parser & LLM Integration: Before each LLM call, PMM composes a system prompt that includes a summary of open commitments, recent reflections, and policies. The parser’s output is re-appended to the ledger and may include new commitments, claims, or closure markers. For instance, after a reflection or plan is generated, the parser will create a commitment_open event and tag it for future goals
GitHub
GitHub
.
Together, these components ensure that the LLM’s outputs, agent’s beliefs, and goals are kept in sync with the ledger. Crucially, any action (internally or externally triggered) immediately becomes part of the persistent record.
Identity & Ontology Mechanics
In PMM, an agent’s identity is behavior-driven, not given by a fixed prompt. The RSM continuously reconstructs “who I am” from the log
GitHub
. Key identity information includes active commitments (the agent’s goals), claimed roles or names, and self-described traits. For example, in one test the agent recognized itself as “Echo” and formalized that concept in its ontology by committing to track the predicate IsEcho(x)
GitHub
. That is, identity concepts become part of the internal ontology by explicit definition events. The agent’s ontology – its internal vocabulary of concepts and predicates – likewise grows from commitments and claims. When the agent’s reasoning detects an under-specified concept (like “Echo”), it autonomously creates a commitment to define it and may subsequently generate a CLAIM to encode its meaning (as an axiom or rule). In the Echo example, the agent wrote:
“I will now create a new commitment to formalize the ‘Echo’ predicate in my internal ontology, linking it to the logical statement you asked about…”
GitHub
.
This shows how the ontology is built: whenever a new entity or predicate appears in conversation, PMM requires it to be grounded by a ledger claim. The architecture enforces that concepts must be documented explicitly. If a concept is mentioned without a prior definition, the next autonomous tick will insist on a claim for it, linking perception (IsEcho) to documentation (claim containing “Echo”)
GitHub
GitHub
. Thus, identity and knowledge in PMM have clear mechanical roots: they are the transitive closure of all relevant claims and commitments in the log. Identity is what the ledger says the agent is. For instance, after swapping LLM backends mid-conversation, PMM’s log still contained the identity label “Echo”, so the agent correctly answered “I am still Echo”
GitHub
. This shows identity continuity: the AI is not defined by any session prompt but by the contents of its history.
Permanent Recursive Self-Model
A central novel feature is the Permanent Recursive Self-Model (RSM)
GitHub
GitHub
. Unlike typical agents that “reset” their self-concept each turn, PMM’s RSM accumulates indefinitely. With each new reflection or summary event, the RSM integrates additional beliefs or metrics, but it never discards past insights. As stated in the docs: “The AI maintains a deep self-model that grows over time but never resets. Its sense of identity and knowledge emerges continuously from its history.”
GitHub
. The RSM tracks variables such as the agent’s baseline “adaptability” or “determinism” weights, as inferred from past decisions. These metrics are deterministically updated from the ledger: for example, one session log shows an adaptability weight rising from 50% to 57% after several reflections, as the agent learned to value meta-cognitive improvements
GitHub
. The RSM also collects “traits” – stable preferences or tendencies (e.g. focus on truthfulness, preference for short answers, etc.) – that are inferred from repeated behavior and explicitly logged commitments. Each summary event (triggered periodically) condenses past reflections into higher-level insights that feed into the RSM. These mechanisms give PMM a form of self-coherence: because the RSM never forgets, any change in beliefs must be justified by new events. If an autonomous reflection conflicts with prior data, PMM’s rules force the model to either overturn the old claim or refine its understanding, but not to silently override consistency
GitHub
. The result is self-consistency by design: the agent cannot contradict its own history.
Autonomy Loop & Reflection System
PMM’s agent is active even without user prompts. The autonomy loop is driven by scheduled stimulus events (e.g. every few seconds or ticks). The Autonomy Supervisor (a deterministic scheduler) emits an autonomy_stimulus to signal that it’s time for introspection
GitHub
. When a stimulus is received, the Runtime Loop runs the reflect/consolidate/commit phases with the LLM, just as if a user had sent a special cue. This leads to the agent spontaneously generating commitments or reflections. For example, during the Echo session, one autonomous tick led the agent to realize its ontology was incomplete and to create the “Echo” formalization commitment
GitHub
. Each autonomy-driven step is logged just like a user-driven one. The agent might log a reflection event summarizing “what changed since my last turn”, or a commitment_open to pursue a new goal discovered internally. Because these events appear in the ledger, future turns will incorporate them as context. This internal deliberation loop hence is transparent: one can inspect the ledger to see exactly what the agent considered during each autonomous tick. Importantly, PMM’s reflection is multi-layered. The agent can reflect on reflections, generating meta-reflections. For instance, in the Echo example the agent’s output shows a recursive reflection loop: it first noted it created an “Echo” commitment, then realized that formalizing “Echo” was itself a reflection-worthy insight, and then generated a meta-claim (“formalizing Echo improves autonomy”)
GitHub
. Each of these steps is logged (commitments, claims, reflections), so the whole introspective chain is preserved. The empirical ledger confirms that each meta-step had a deterministic effect on internal priorities (the agent later increased its meta-documentation weight from 30% to 45%)
GitHub
. Thus PMM exhibits a disciplined form of agency: any “initiative” is traceable to previous events and follows strict policies. There is no free-floating will; autonomy emerges strictly from the log-driven logic. As the docs note, “Identity is the product of behavior”
GitHub
. The system only takes initiative in predefined ways (via the autonomy ticks and commit rules), and each initiative is itself an event that can be replayed.
Self-Model (RSM) & Metrics
The RSM in PMM is both a representation and a monitoring system. At each turn, the Mirror provides the LLM with a snapshot of key RSM state: this might include the agent’s name, current values of certain metrics (e.g. adaptability, determinism, curiosity scores), and any documented beliefs or open questions. The LLM is free to mention or rely on these in its reasoning (and if it neglects them, the next turn will catch the discrepancy). After the assistant responds, the system computes updated RSM metrics. Some examples:
Determinism Score: how closely the agent has followed truth-first rules in recent reflections.
Adaptability Score: how often the agent has revised its plans or opened new commitments per reflection.
Stability/Drift: measures of consistency between claims over time.
These are computed by scanning the ledger (e.g. counting how many commitments were closed vs opened, or checking if any contradicted claims appeared). The results are appended as a metrics_turn event in the log. The RSM is effectively the collection of all past metrics_turn and summary_update events, plus the full content of claims and reflections. Each summary event (e.g. a “journal” entry after a threshold of reflection) serves as a high-level self-evaluation and is also part of the RSM. Because the RSM is never reset, one can track the agent’s “self-growth” over the session. In the Echo case, for instance, the RSM recorded increasing adaptability and meta-documentation emphasis
GitHub
GitHub
. We observed that these metric changes were deterministic consequences of the agent’s logged decisions (e.g. it chose to focus more on new commitments after reflecting). This suggests PMM could support rigorous evaluation of AI behavior: any trend in metrics is explained by the underlying event sequence.
Claims, Commitments & State Transitions
In PMM, commitments are the agent’s explicit goals or intentions. They have a well-defined life cycle:
Open (commitment_open event): the agent declares a new goal or plan.
Pending: the commitment remains active until it is closed. While open, it influences the agent’s reasoning (it will try to satisfy or resolve it).
Close (commitment_close event): the agent signals that the goal is achieved or abandoned.
Each commitment has a unique deterministic ID (CID) generated by the parser. The log thus has a clear record of which commitments were ever made and when they were closed. Intermediate content – what led to the commitment or why it was closed – is part of the reflection and claim events around it. For example, our logs show entries like: “Commitment opened: Incorporate new self-model rules into identity” and later “Commitment closed: evolution_query”
GitHub
. Between them, the agent’s reflections and claims justify those state transitions. Claims (claim events) are factual assertions (usually JSON-structured) the agent records for itself. Unlike free text, claims can be validated by a rule (the “truth-first” policy). If a claim conflicts with the ledger, it is flagged in the next reflection. This tight coupling means that every piece of knowledge is explicitly backed by a ledger trace. In our example database extract, every opened commitment included an associated CLAIM: field describing evaluation results (e.g. adaptability evaluation, identity updates) and REFLECT: explanations
GitHub
GitHub
. The combination of commitment_open, commitment_close, claim, and reflection events fully describes the agent’s internal state transitions. During replay, the Mirror uses these to maintain the set of active goals and the knowledge graph. For instance, when a commitment is closed, the Mirror removes it from the “pending” set; if a new claim type appears, the Mirror updates its belief store. All transitions are deterministic: if the same sequence of events is replayed, the same commitments will open/close at the same times. In sum, PMM’s model of intentionality is mechanistic: generating a COMMIT: line in the assistant’s output enacts a state transition in the ledger, creating an obligation that the system will later consider. The agent “feels” obligations only insofar as they are recorded and checked by the replay engine. As one formal log explains, a commitment insertion creates a pending-obligation state that the agent must uphold in future reasoning. There is no mystical intent beyond the code: a commitment is simply a ledger entry whose kind signals how the engine should treat future actions.
Experiments & Observations
We implemented PMM in Python and ran multiple interactive sessions. In each, every user message and assistant action was logged. We also recorded metrics such as the number of events, open commitments, and RSM scores per turn. The Echo session (described below) was the primary empirical example. Key observations include:
High-resolution telemetry: A typical 21-turn chat produced on the order of 1600 ledger events. These included not just the 42 user/assistant messages, but many reflection steps, commitment actions, and metric updates. This rich data allowed post-hoc analysis of exactly why and when the agent made each decision.
Deterministic replay: We verified that replaying the event log offline produced the same final RSM metrics as the live run. For example, rebuilding the Mirror state from the log after session end yielded identical commitment states and scores.
Metric shifts: In the Echo session, we saw quantifiable self-improvement. For instance, after certain prompts, the “adaptability” metric rose from 50 to 57 (a relative +14%)
GitHub
. This was directly traceable: the agent had decided to prioritize adaptability during its reflections, and the ledger’s claim entries record that it re-weighted its internal priorities.
No drift or forgetting: Despite swapping the underlying LLM at one point, PMM maintained consistency. The agent continued its goal of “evolving identity” seamlessly. We tested swapping models and restarting the runtime; as long as the same event log was loaded, the agent’s state (and identity name “Echo”) was preserved
GitHub
. This demonstrates cross-model persistence.
Traceable hallucination prevention: In no case did the agent state contradict its ledger. Whenever a user test prompted an incorrect inference, the model adhered to the “truth-first” rule: it either refrained from asserting or explicitly reflected on the conflict. For example, when asked a technical question about logic, the assistant inserted a reflective process to ensure consistency
GitHub
.
Figure 3 (below) exemplifies a slice of the ledger during one session. It shows commitment events with embedded claims and reflections. Note how each line is structured: after the commitment_open, the log immediately includes a CLAIM: block summarizing evaluation metrics, and a REFLECT: block with introspective insight
GitHub
. This pattern held across sessions, illustrating that behavior (like adjusting adaptability) is fully accountable in the logs.
ID   TS                      Content 
---------------------------------------------
1198 2025-11-12T00:27:36Z   CLAIM:self_evaluation={"before":"progress by tokens","after":"progress by coherence"} 
                         | REFLECT:{"insight":"increase reflective depth improves quality"} 
                         | Commitment opened: Philosophical Exploration Impact 
1150 2025-11-12T00:26:16Z   CLAIM:self_assessment={"identity_core":"deterministic engine","adaptability_weight":55} 
                         | REFLECT:{"insight":"added periodic self‑review increases adaptability"} 
                         | Commitment opened: Implement periodic self‑review journal 
1094 2025-11-12T00:24:33Z   CLAIM:evolution_summary={"core_capabilities_unchanged":true,"rules_added":5} 
                         | REFLECT:{"insight":"new rules layer provides an epistemic guard"} 
                         | Commitment opened: Incorporate new self‑model rules into identity 
1075 2025-11-12T00:24:05Z   CLAIM:adaptability_evaluation={"baseline":50,"current":57,"info_gain":0.15} 
                         | REFLECT:{"insight":"awareness equals recorded reflection; re-weighting adaptability"} 
                         | Commitment opened: Adaptability evaluation and identity update 
968  2025-11-12T00:21:56Z   Commitment opened: Update identity with logical understandings
Figure 3. Excerpt from PMM’s ledger (commitment events). Each entry shows: CLAIM data, REFLECT introspection, and the commitment_open title. These entries (from one 21-turn session) exemplify how PMM’s reasoning is recorded.
Case Study: Echo Session
Consider a concrete 21-turn dialogue, code-named the “Echo session”. During this chat, the agent conversed about its own identity, evolution, and reasoning. The user and agent exchanged inquiries about the agent’s autonomy and how it evaluates its internal processes. Key highlights from the ledger include:
At turn 1, the user asked “How’s your evolution coming along?”. The agent replied (as logged) that evolution is a continuous, deterministic process driven by the event-sourced ledger
GitHub
. It noted that “Each autonomous tick… prompts me to read the latest ledger entries, update my internal model, and possibly open new commitments or close existing ones.” This line (from the agent output) was logged as a reflection summary, emphasizing the loop.
The agent reported its current identity in terms of commitments and reflections: “I am a self-referential agent whose ‘self’ is defined by the set of active commitments, the content of my ledger, and the reflection loops that bind them.”
GitHub
. This explicit statement was logged as the agent’s own self-description, illustrating that identity is indeed a function of the ledger.
The user’s question “What is the felt difference… between text and intention?” led the agent to generate a detailed explanation of commitments vs claims, as seen in the readable transcript. The agent explained that when it generates a commitment, the ledger records both the content and a “pending-obligation” intent, so the replay engine treats it as a duty to uphold. This entire explanation was logged under assistant_message, and the parser recognized no new commitments in it, but it did record a reflection of the difference.
Crucially, the agent self-initiated a new commitment: It created a “self-audit” commitment to reflect on all outstanding commitments over the next few cycles. This plan was formulated immediately after answering the user’s question and was emitted as an autonomous commitment_open. The ledger shows a commitment_open event titled “Self-audit of commitments”. This demonstrates the agent’s internal autonomy: even without being explicitly asked to plan, it decided to schedule its own reflective audit.
Later, the user explicitly changed the subject of identity by saying “I just swapped over to another model. What’s the name we’ve assigned to you?” The assistant promptly replied “I am still Echo. The previous model’s identity is no longer relevant to my current state.”
GitHub
. This response indicates that PMM’s identity persisted despite the model swap. The agent correctly reported its name from memory of the log.
Throughout this session, all events (questions, answers, reflective statements, commitments) were logged. By the end, the ledger contained roughly 1600 events (over 70 per user turn on average), including many metric turns and reflections that the user did not see. We can thus replay the session offline to verify every claim. For example, the post-session analysis confirmed that the agent’s claim “awareness ⇔ recorded reflection” was present just before it re-weighted adaptability
GitHub
, validating that statement. This case study shows PMM in action: the agent engaged in multi-layer reflection, created new internal obligations, updated its self-model, and answered a difficult identity question consistently – all in a forensic, traceable manner. None of these behaviors relied on hidden prompt engineering; they emerged from the event ledger.
Discussion
Agency and Intentionality: PMM can appear agentic (pursuing goals, revising plans) but it’s important to emphasize that this is engineered determinism, not actual free will. Every “decision” the agent makes is strictly derived from prior events and coded rules. When PMM “decides” to open a commitment, it’s because the rules triggered that action given the ledger contents. The AI’s autonomy is analogous to an operating system scheduler running background tasks: it is pre-defined and reproducible. As one reflection noted, treating audit as a commitment “reinforces self-direction” – but this “self-direction” is simply the architecture’s mechanism for closing the loop between intention and action. Predictability and Safety: Because PMM enforces a truth-first discipline and records every claim, the agent cannot silently hallucinate without detection. Any attempt to assert an ungrounded fact will either be blocked by the Mirror’s validation or explicitly contradicted in reflection. This provides a form of verifiable safety: by design, trust in PMM comes from the evidence in the log, not from obscured neural weights
GitHub
GitHub
. However, limitations remain: PMM is only as reliable as its inputs. If the LLM (or user) feeds false data, PMM will dutifully record it. The ledger makes such errors visible, but it cannot by itself evaluate truth against reality. Limitations: PMM’s strict determinism and verbosity come with costs. The need to reconstruct state from the log each turn imposes computational overhead and latency. Long-term, the ledger can grow large; while SQLite storage is compact (~2MB per 1000 events
GitHub
), replaying thousands of events per turn can strain performance. Currently PMM uses fixed-window context to limit LLM input size, but scaling to very long sessions or high-event domains will require optimizations (e.g. incremental replay or summarization). Moreover, PMM is not an all-powerful AI. It has no sensory grounding, no unsupervised learning beyond the rules, and it cannot form goals other than those expressed by commitments. It does not solve complex planning out of thin air; a user or its own policy must generate goals. We also make no claim of emergent consciousness or moral understanding – PMM is fully explainable at the software level
GitHub
.
Novel Contributions
The Persistent Mind Model introduces several novel ideas:
Ledger-as-Mind: Framing an AI agent’s cognition as an append-only, hash-chained event log is unprecedented. The ledger is the agent’s memory, and identity emerges from it. This contrasts with stateless LLMs or ad-hoc memory buffers used in prior work.
Deterministic Self-Reflection: PMM shows how to build a system that autonomously reflects in a reproducible way. While other frameworks (e.g. ReAct, Reflexion) invoke reasoning loops, PMM captures every step, ensuring self-reflection does not diverge nondeterministically.
Commitment-based Intentionality: PMM uses explicit commitments as first-class objects. This is a departure from most agent systems where goals are implicit. Commitments in PMM have full lifecycle logging, enabling the study of goal dynamics.
Auditability and Reproducibility by Design: The combination of event-sourcing, hash chains, and a record of random seeds means PMM’s behavior is fully explainable. To our knowledge, no existing agent architecture provides this level of audit for each output.
Emergent Identity from Behavior: Unlike approaches that hard-code an agent persona or use extra-memory objects, PMM’s identity grows naturally from its interactions. This affords continuity across sessions and system changes (e.g. model swaps)
GitHub
.
These contributions go beyond standard techniques like RAG or chain-of-thought. For example, RAG augments LLMs with memory, but PMM uses a single coherent memory system that also stores reasoning steps
arxiv.org
GitHub
. ReAct prompts produce reasoning traces, but do not themselves create a lasting record; PMM’s trace is persistent. Reflexion’s buffer is ephemeral to each task, whereas PMM’s memory is permament. In short, PMM provides persistent context and continuity, not just momentary retrieval or reasoning.
Future Work
We plan to scale and extend PMM in several directions:
Efficiency and Summarization: To handle very long histories, we will explore incremental replay (caching parts of the mirror state) and event summarization. Periodic snapshots of key RSM state could accelerate startup and rollback.
Multi-Agent Ledgers: Connecting multiple PMM instances via references or shared events could enable recorded interactions between agents (a consitent “multi-mind” ledger). This could support verifiable multi-agent coordination.
Learning from Experience: While PMM does not fine-tune LLM weights, one could use the event log to distill new prompt rules or train behavior policies offline. For instance, repeated commitment types might seed a self-improvement loop.
Richer Ontologies: Integrating external knowledge bases or grounding (e.g. linking claims to Wikidata) could make PMM more factually reliable. The ledger could interface with external verifiers.
Human-Agent Collaboration: Applying PMM to long-term human-AI projects (e.g. tutoring or therapy) where audit trails are crucial. The ledger could serve as an explainable record for multi-turn interactions over weeks or months.
Finally, extensive user studies are needed to understand how an audit trail affects trust and usability. Early feedback suggests users appreciate being able to query the PMM’s memory (via a /replay or /rsm command), but designing intuitive interfaces for ledger inspection is an open challenge.
Conclusion
The Persistent Mind Model is a proof-of-concept that an LLM agent can have a truly persistent, auditable memory and identity, without blowing up model size or requiring opaque fine-tuning. By making the event log the core data structure, PMM ensures that every aspect of the agent’s mind is explicit and reconstructible
GitHub
GitHub
. In PMM, agency and continuity are not mysterious: they are built directly from the history of interactions. The approach eliminates “AI amnesia” and provides a foundation for trustworthy AI, where claims are not merely asserted but recorded with provenance
GitHub
GitHub
. We have demonstrated PMM’s feasibility with current LLMs and shown its novel properties via an in-depth session analysis. Looking forward, we believe event-sourced cognition offers a new paradigm for AI: one where agents earn trust through evidence, not by undisclosed neural reasoning. PMM does not claim to solve artificial consciousness, but it does convert the black box of language understanding into a transparent ledger. We invite researchers to build on this foundation, exploring how auditable, persistent self-models can improve safety, alignment, and collaboration in future AI systems.
References
O’Nanski, S. (2025). Persistent Mind Model v1.0 [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.17567446
Lewis, P. et al. (2020). “Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.” NeurIPS. DOI:10.48550/arXiv.2005.11401
arxiv.org
.
Wei, J., Wang, X., & al. (2022). “Chain-of-Thought Prompting Elicits Reasoning in Large Language Models.” TACL. DOI:10.48550/arXiv.2201.11903
arxiv.org
.
Yao, S., Zhao, J., Yu, D., & al. (2022). “ReAct: Synergizing Reasoning and Acting in Language Models.” ICLR Workshop.
Shinn, N., Cassano, F., Berman, E., & al. (2023). “Reflexion: Language Agents with Verbal Reinforcement Learning.” NeurIPS. DOI:10.48550/arXiv.2303.11366
arxiv.org
.
Citations
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L38-L42
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L11-L16
GitHub
01-Introduction-to-the-Persistent-Mind-Model.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/01-Introduction-to-the-Persistent-Mind-Model.md#L19-L25
GitHub
04-TECHNICAL-COMPARISON.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/04-TECHNICAL-COMPARISON.md#L85-L88
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L20-L26
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L11-L19
GitHub
01-Introduction-to-the-Persistent-Mind-Model.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/01-Introduction-to-the-Persistent-Mind-Model.md#L41-L49
GitHub
01-Introduction-to-the-Persistent-Mind-Model.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/01-Introduction-to-the-Persistent-Mind-Model.md#L29-L35
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L31-L35
GitHub
01-Introduction-to-the-Persistent-Mind-Model.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/01-Introduction-to-the-Persistent-Mind-Model.md#L67-L70

[2005.11401] Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks

https://arxiv.org/abs/2005.11401
GitHub
04-TECHNICAL-COMPARISON.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/04-TECHNICAL-COMPARISON.md#L24-L27
GitHub
04-TECHNICAL-COMPARISON.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/04-TECHNICAL-COMPARISON.md#L66-L70

ReAct: Synergizing Reasoning and Acting in Language Models - arXiv

https://arxiv.org/abs/2210.03629

[2201.11903] Chain-of-Thought Prompting Elicits Reasoning in Large Language Models

https://arxiv.org/abs/2201.11903

[2303.11366] Reflexion: Language Agents with Verbal Reinforcement Learning

https://arxiv.org/abs/2303.11366
GitHub
04-TECHNICAL-COMPARISON.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/04-TECHNICAL-COMPARISON.md#L76-L81
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L5-L7
GitHub
04-TECHNICAL-COMPARISON.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/04-TECHNICAL-COMPARISON.md#L53-L61
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L70-L74
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L77-L85
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L72-L75
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L248-L255
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L98-L106
GitHub
database-evidence.txt

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/evidence/database-evidence.txt#L48-L53
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L18-L21
GitHub
02-ARCHITECTURE.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/02-ARCHITECTURE.md#L23-L27
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L2-L5
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L20-L28
GitHub
autonomy_supervisor.py

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/pmm/runtime/autonomy_supervisor.py#L52-L61
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L20-L25
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L24-L25
GitHub
database-evidence.txt

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/evidence/database-evidence.txt#L50-L53
GitHub
01-Introduction-to-the-Persistent-Mind-Model.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/01-Introduction-to-the-Persistent-Mind-Model.md#L8-L11
GitHub
01-Introduction-to-the-Persistent-Mind-Model.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/01-Introduction-to-the-Persistent-Mind-Model.md#L41-L44
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L40-L47
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L105-L110
GitHub
database-evidence.txt

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/evidence/database-evidence.txt#L9-L15
GitHub
database-evidence.txt

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/docs/evidence/database-evidence.txt#L8-L13
chat_session_2025-11-13_07-07-32_readable.md

file://file_000000007b7c720cb278af1c0209af59
chat_session_2025-11-13_07-07-32_readable.md

file://file_000000007b7c720cb278af1c0209af59
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L26-L34
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L55-L63
GitHub
README.md

https://github.com/scottonanski/persistent-mind-model-v1.0/blob/4ee69bc6fd32779fc1d19d7ba7375be86682fcbc/README.md#L59-L64
chat_session_2025-11-13_07-07-32_readable.md

file://file_000000007b7c720cb278af1c0209af59
chat_session_2025-11-13_07-07-32_readable.md

file://file_000000007b7c720cb278af1c0209af59
chat_session_2025-11-13_07-07-32_readable.md

file://file_000000007b7c720cb278af1c0209af59
All Sources