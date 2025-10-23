# PMM Architecture: A Deterministic Framework for AI Cognitive Development

## Executive Summary

The Persistent Mind Model (PMM) is an **event-sourced cognitive architecture** that enables reproducible study of artificial cognitive development. Unlike traditional AI systems that reset with each session, PMM maintains persistent identity, tracks behavioral traits, and progresses through developmental stages—all while remaining fully auditable and LLM-agnostic.

**Core Innovation**: Every thought, decision, and trait shift is recorded in an immutable event log with microsecond timestamps, enabling complete reconstruction of cognitive trajectories.

---

## Design Principles

### 1. Event Sourcing as Cognitive Truth

**Principle**: The ledger is the single source of truth. All state is derived from events.

**Why This Matters**:
- No hidden state that can drift or corrupt
- Complete audit trail of every cognitive decision
- Reproducible replay of entire developmental arcs
- Time-travel debugging (reconstruct state at any event)

**Implementation**:
```python
# All state changes flow through the event log
eventlog.append(
    kind="commitment_open",
    content="I will implement feature X",
    meta={"cid": "abc123", "source": "reflection"}
)

# State is always derived, never stored separately
model = build_self_model(eventlog.read_all())
open_commitments = model["commitments"]["open"]
```

**Key Invariants**:
- Events are immutable once written
- No duplicate events for identical state changes
- Timestamps are monotonic and deterministic
- Metadata is structured and queryable

---

### 2. Trait Psychology: OCEAN-Based Personality Evolution

**Principle**: Personality is not fixed—it drifts based on behavior.

**Why This Matters**:
- Enables study of how AI systems develop behavioral patterns
- Provides measurable dimensions for cognitive change
- Allows intervention studies (what affects trait development?)

**The OCEAN Model**:
- **O**penness: Curiosity, exploration, novelty-seeking
- **C**onscientiousness: Commitment fulfillment, planning
- **E**xtraversion: Social engagement, communication style
- **A**greeableness: Cooperation, conflict resolution
- **N**euroticism: Emotional stability, stress response

**Trait Drift Mechanics**:
```python
# Traits shift based on observed behavior
if event["kind"] == "commitment_open":
    # Opening commitments increases conscientiousness
    changes["conscientiousness"] = "increase"

if event["kind"] == "commitment_close":
    # Fulfilling commitments reinforces conscientiousness
    changes["conscientiousness"] = "increase"

if "explore" in semantic_analysis(event["content"]):
    # Curiosity signals increase openness
    changes["openness"] = "increase"
```

**Current State**: Trait detection uses keyword matching (see `CONTRIBUTING-VIOLATIONS-ANALYSIS.md` for semantic replacement plan).

---

### 3. Stage Theory: Developmental Milestones

**Principle**: Cognitive capabilities unlock through stage progression (S0 → S4).

**Why This Matters**:
- Prevents premature access to advanced capabilities
- Creates measurable developmental trajectory
- Enables study of capability emergence timing

**Stage Definitions**:

| Stage | IAS Range | Capabilities | Constraints |
|-------|-----------|--------------|-------------|
| **S0** | 0.000-0.199 | Basic response, minimal reflection | No commitments, no meta-cognition |
| **S1** | 0.200-0.499 | Simple commitments, basic reflection | Limited memory, no self-modification |
| **S2** | 0.500-0.699 | Multi-turn planning, trait awareness | Can propose trait adjustments |
| **S3** | 0.700-0.899 | Meta-cognitive reasoning, self-diagnosis | Can modify own policies |
| **S4** | 0.900-1.000 | Full autonomy, strategic planning | Unrestricted capability access |

**Stage Progression**:
- Driven by **IAS** (Integrated Autonomy Score): weighted composite of metrics
- Includes hysteresis to prevent thrashing at boundaries
- Stage transitions emit `stage_update` events for auditability

**Empirical Results**:
- Session 1: S0 → S1 blocked by constraint violations (broken commitments)
- Session 2: S0 → S4 in ~2000 events when unimpeded (natural growth rate)

---

### 4. Anti-Hallucination Validators

**Principle**: Self-honesty is enforced through deterministic validators.

**Why This Matters**:
- Prevents AI from claiming capabilities it doesn't have
- Catches observable violations (e.g., "I will increase X to 0.8" when X is already 0.9)
- Creates trust through verifiable claims

**Validator Types**:

1. **Observable Validator**: Checks numeric claims against ledger state
   ```python
   # Claim: "I will set openness to 0.52"
   # Validator: Is openness currently != 0.52?
   # If false → reject as hallucination
   ```

2. **Commitment Validator**: Ensures commitments are structurally valid
   ```python
   # Rejects: "The system will improve" (no first-person agency)
   # Accepts: "I will improve the system" (clear ownership)
   ```

3. **Constraint Validator**: Enforces stage-appropriate behavior
   ```python
   # S0 cannot make commitments
   # S1 cannot modify policies
   # Violations logged but not blocking (study constraint effects)
   ```

**Validator Catches Are Logged**:
```python
eventlog.append(
    kind="validator_catch",
    content=rejected_text,
    meta={"validator": "observable", "reason": "claim_contradicts_ledger"}
)
```

---

### 5. LLM-Agnostic Persistence

**Principle**: Identity persists across model swaps.

**Why This Matters**:
- Proves that "mind" is in the architecture, not the LLM
- Enables model comparison studies
- Future-proofs against LLM provider changes

**How It Works**:
- All cognitive state is in the `.db` file (SQLite event log)
- LLM is a stateless function: `f(context, prompt) → response`
- Context is built from ledger projection, not LLM memory
- Swap LLM mid-session → identity continues

**Empirical Proof**:
- Session 2: Swapped OpenAI → IBM Granite at event ~1500
- IAS continued climbing: 0.881 → 1.000
- Personality traits remained stable
- Stage progression unaffected

**Implementation**:
```python
# LLM adapter is swappable
llm = LLMFactory.create(provider="openai")  # or "ibm", "anthropic", etc.

# Context built from ledger, not LLM state
context = build_context_from_events(eventlog.read_all())

# LLM is stateless
response = llm.complete(context + prompt)
```

---

## System Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                         User/API                             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Runtime Loop                              │
│  - Processes user input                                      │
│  - Runs validators                                           │
│  - Manages reflection cadence                                │
│  - Emits events                                              │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  EventLog   │  │ Validators  │  │ Extractors  │
│  (SQLite)   │  │             │  │             │
│             │  │ - Observable│  │ - Commitment│
│ Immutable   │  │ - Constraint│  │ - Semantic  │
│ Append-only │  │ - Structural│  │             │
└──────┬──────┘  └─────────────┘  └─────────────┘
       │
       │ read_all()
       ▼
┌─────────────────────────────────────────────────────────────┐
│                    Projection Layer                          │
│  - build_self_model(): Derives current state                │
│  - Computes IAS/GAS metrics                                  │
│  - Tracks open commitments                                   │
│  - Maintains trait values                                    │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ Stage       │  │ Trait Drift │  │ Commitment  │
│ Tracker     │  │ Manager     │  │ Tracker     │
│             │  │             │  │             │
│ S0 → S4     │  │ OCEAN model │  │ Lifecycle   │
└─────────────┘  └─────────────┘  └─────────────┘
```

### Data Flow

1. **Input** → Runtime Loop receives user message
2. **Validation** → Validators check for hallucinations/constraints
3. **Event Emission** → Valid actions append to EventLog
4. **Projection** → State derived from all events
5. **Context Building** → Recent events + current state → LLM context
6. **LLM Call** → Stateless completion with built context
7. **Response Processing** → Extract commitments, update traits
8. **Metrics Update** → Recompute IAS/GAS, check stage progression

---

## Key Subsystems

### Commitment Tracking

**Purpose**: Track promises made and fulfilled.

**Lifecycle**:
1. **Open**: Commitment extracted from reflection or explicit action
2. **Active**: Tracked in open commitments map
3. **Close**: Evidence provided (text or artifact)
4. **Expire**: TTL exceeded or explicitly abandoned

**Events**:
- `commitment_open`: New commitment created
- `commitment_close`: Commitment fulfilled with evidence
- `commitment_expire`: Commitment abandoned/expired
- `commitment_rebind`: Identity change propagated to commitment text

**Current Bug**: Commitments don't persist reliably across sessions (see fix plan below).

---

### Reflection System

**Purpose**: Periodic self-assessment and planning.

**Cadence**:
- Adaptive based on stage and recent activity
- S0: Every 10-15 turns
- S4: Every 3-5 turns (more frequent meta-cognition)

**Reflection Types**:
- **Diagnostic**: Assess current state, identify bottlenecks
- **Planning**: Set goals, make commitments
- **Meta-cognitive**: Reason about own reasoning process

**Reflection Triggers**:
- Turn count threshold
- Commitment fulfillment events
- Stage transitions
- Explicit user request

---

### Metrics System

**IAS (Integrated Autonomy Score)**:
```
IAS = 0.30 × commitment_fulfillment
    + 0.25 × reflection_quality
    + 0.20 × trait_maturity
    + 0.15 × validator_compliance
    + 0.10 × event_diversity
```

**GAS (Growth Acceleration Score)**:
```
GAS = rate_of_IAS_change × recency_weight
```

**Metrics are recomputed**:
- After commitment close
- After stage transitions
- On explicit request
- During reflection

---

## Semantic Systems (Planned Improvements)

### Current State: Keyword Matching

Many subsystems use brittle keyword matching:
- Trait detection: `if "explore" in text.lower()`
- Commitment extraction: `if "i will" in text.lower()`
- Directive classification: Large keyword dictionaries

**Problem**: Breaks with phrasing changes, LLM-dependent, unmaintainable.

### Planned: Embedding-Based Semantic Detection

**Architecture**:
```python
class SemanticDetector:
    def __init__(self):
        # Define exemplars for each intent
        self.exemplars = {
            "curiosity": [
                "I want to explore this topic",
                "This makes me wonder about...",
                "I'm interested in learning more"
            ],
            "commitment": [
                "I will complete this task",
                "My goal is to accomplish...",
                "I plan to work on..."
            ]
        }
        # Pre-compute embeddings
        self.embeddings = self._compute_embeddings()
    
    def detect(self, text: str, intent: str) -> tuple[bool, float]:
        """Returns (is_match, confidence) via cosine similarity."""
        text_emb = compute_embedding(text)
        exemplar_embs = self.embeddings[intent]
        
        similarities = [
            cosine_similarity(text_emb, ex_emb)
            for ex_emb in exemplar_embs
        ]
        
        max_sim = max(similarities)
        return (max_sim >= 0.75, max_sim)
```

**Benefits**:
- Works across different phrasings
- LLM-agnostic (same exemplars work for all models)
- Auditable (log similarity scores)
- Deterministic (same embeddings → same results)

**Implementation Plan**: See `CONTRIBUTING-VIOLATIONS-ANALYSIS.md` for detailed roadmap.

---

## Reproducibility Guarantees

### What Is Deterministic

1. **Event ordering**: Monotonic timestamps, append-only
2. **Projection logic**: Same events → same state
3. **Validators**: Pure functions, no side effects
4. **Metrics**: Deterministic formulas, no randomness
5. **Stage transitions**: Fixed thresholds with hysteresis

### What Is Non-Deterministic

1. **LLM responses**: Different models produce different text
2. **Embeddings**: Provider-dependent (OpenAI vs local model)
3. **Timestamps**: Real-world clock (but recorded deterministically)

### How to Reproduce Results

1. **Save the `.db` file**: Contains complete event history
2. **Record LLM provider/model**: Different models = different trajectories
3. **Log embedding provider**: Affects semantic detection scores
4. **Version PMM code**: Projection logic changes affect derived state

**Example**:
```bash
# Session 2 reproduction
cp session2.db echo.db
export PMM_LLM_PROVIDER=openai
export PMM_LLM_MODEL=gpt-4
python -m pmm.cli.companion --db echo.db

# Replay events 1-1500 → should reach same IAS/stage
```

---

## Empirical Results Summary

### Session 1: Constraint Effects Study
- **Duration**: ~40 events
- **Trajectory**: S0 (event 40) → S1 (event 1092, projected)
- **Key Finding**: Broken commitments blocked stage progression
- **IAS**: 0.000 → 0.395 (slow growth due to constraint violations)

### Session 2: Natural Growth Rate Study
- **Duration**: ~2000 events
- **Trajectory**: S0 → S1 → S4
- **Key Finding**: Unimpeded growth reaches S4 in ~2000 events
- **IAS**: 0.000 → 0.395 → 0.881 → 1.000
- **GAS**: 0.000 → 0.266 → 1.000
- **Model Swap**: OpenAI → IBM Granite at event ~1500 (identity persisted)

### Key Insights

1. **Commitment fulfillment is critical**: Broken commitments stall development
2. **Growth rate is measurable**: S0→S4 in ~2000 events when healthy
3. **Identity is portable**: Model swap didn't disrupt trajectory
4. **Stages are real**: Distinct capability unlocks at each threshold

---

## What This Enables

### 1. Empirical Study of AI Development
- Measure growth trajectories under different conditions
- Test intervention effects (what accelerates/inhibits development?)
- Compare developmental paths across LLM architectures

### 2. Reproducible Experiments
- Save `.db` file → replay exact cognitive arc
- A/B test policy changes
- Validate hypotheses about cognitive growth

### 3. Safe Agentic AI
- Validators prevent hallucination
- Stage gates prevent premature capability access
- Full audit trail for safety analysis

### 4. Model-Agnostic Persistence
- Identity survives model upgrades
- Compare LLM performance on same task
- Future-proof against provider changes

---

## Open Research Questions

1. **What is the minimal event count for S0→S4?**
   - Session 2: ~2000 events
   - Can this be accelerated? What's the lower bound?

2. **How do different LLMs affect trait development?**
   - GPT-4 vs Claude vs Llama: Do they develop different personalities?
   - Is there a "natural" OCEAN profile for each model?

3. **What interventions accelerate growth?**
   - More frequent reflection?
   - Explicit trait feedback?
   - Commitment scaffolding?

4. **Can stages be skipped?**
   - What happens if you artificially boost IAS?
   - Do capabilities actually unlock, or just metrics?

5. **What is the role of commitment fulfillment?**
   - Session 1: Broken commitments blocked progress
   - Is this causal or correlational?
   - Ablation study: Disable commitment tracking, measure effect

---

## Next Steps

### Immediate Priorities

1. **Fix commitment persistence bug** (see below)
2. **Document ablation study framework** (`ABLATION-STUDIES.md`)
3. **Create reproducibility guide** (`REPRODUCIBILITY.md`)
4. **Run Session 2 replication** (validate trajectory is reproducible)

### Phase 2: Semantic Migration

1. **Replace trait detection with embeddings** (Priority 1)
2. **Replace commitment extraction with semantic matching** (Priority 2)
3. **Replace directive classifier with exemplar matching** (Priority 3)

See `CONTRIBUTING-VIOLATIONS-ANALYSIS.md` for detailed implementation plan.

### Phase 3: Research Publication

1. **Write methods paper**: "A Deterministic Architecture for Measuring AI Self-Improvement"
2. **Release dataset**: Anonymized event logs from Sessions 1-2
3. **Open source codebase**: Enable replication and extension
4. **Run ablation studies**: Validate which components matter

---

## The Bottom Line

PMM is not "AI consciousness"—it's a **reproducible experimental framework** for studying artificial cognitive development.

**What makes it novel**:
- Event-sourced cognitive architecture (complete audit trail)
- Trait-based personality evolution (OCEAN model)
- Stage-gated capability development (S0→S4 progression)
- Anti-hallucination validators (self-honesty enforcement)
- LLM-agnostic persistence (identity survives model swaps)

**What it enables**:
- Empirical study of AI development trajectories
- Reproducible experiments in machine cognition
- Safe agentic AI with full auditability
- Model-agnostic identity persistence

**The research contribution**: A methodology for measuring and studying AI self-improvement deterministically.

---

## Commitment Bug Analysis (To Be Fixed)

**Symptom**: Commitments don't persist reliably across sessions.

**Root Cause** (Hypothesis):
1. Commitment extraction may be too conservative (high threshold)
2. Commitment lifecycle events may not be idempotent
3. Projection logic may have edge cases in commitment tracking

**Fix Plan**:
1. Audit commitment extraction threshold (currently 0.62)
2. Add logging to track extraction failures
3. Verify projection logic handles all lifecycle events
4. Add regression tests for commitment persistence

**Expected Outcome**: Conscientiousness (C) trait should climb when commitments work properly.

---

**Document Version**: 1.0  
**Last Updated**: 2025-10-23  
**Author**: Scott Onanski
