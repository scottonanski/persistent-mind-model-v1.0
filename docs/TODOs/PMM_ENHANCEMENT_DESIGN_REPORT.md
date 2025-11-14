# PMM Enhancement Design Report
## Self-Directed Evolution Features

**Date**: November 9, 2025  
**Source**: PMM Instance Request (Event ID 3742)  
**Status**: Design Proposal

---

## Executive Summary

This report analyzes five enhancement features requested by a PMM instance during a conversation about self-evolution capabilities. Each feature is evaluated against PMM's core architectural principles: **determinism**, **ledger-based auditability**, and **autonomous operation without user gates**.

The PMM instance identified these priorities:
1. **Adaptive Learning Loops**
2. **Contextual Memory Integration**
3. **Stability-Adaptation Balance**
4. **Identity Fragmentation Management**
5. **Meta-Learning Capabilities**

---

## Architectural Constraints

Per `CONTRIBUTING.md`, all enhancements must satisfy:

### Core Requirements
- **Ledger Integrity**: All behavior reconstructable from event ledger alone
- **Determinism**: No randomness, wall-clock timing, or environment-based logic
- **Autonomy**: Must start at boot, no user-triggered gates (`/tick`, config flags)
- **No Heuristics**: No regex/keyword matching in runtime code
- **Projection Integrity**: Mirror and MemeGraph rebuildable from `eventlog.read_all()`
- **Idempotency**: No duplicate events for unchanged semantic state

### Forbidden Patterns
- External API calls affecting ledger state
- Non-deterministic model invocations in core loops
- Hidden state outside the ledger
- User-triggered autonomy paths

---

## Implementation Guardrails (Aligned with CONTRIBUTING.md)

This design report refines, but does **not** replace, the coding standards in `CONTRIBUTING.md`. All implementation work for these enhancements MUST treat `CONTRIBUTING.md` as the canonical source of truth for runtime behavior and testing.

The key guardrails for implementing these features are:

- **Structured COMMIT/CLAIM/REFLECT parsing**
  - Route all COMMIT/CLAIM/REFLECT extraction through helpers in `pmm.core.semantic_extractor` (and any future structured parsers), never via ad‑hoc string scans in runtime code.
  - Derive semantic tags and higher-level projections from structured outputs (`extract_commitments`, `extract_claims`, reflection parsers), not from `"COMMIT:" in content` or similar keyword checks.
  - New schemas for COMMIT/CLAIM/REFLECT MUST use explicit JSON structures with canonical encoding/decoding, ensuring replay determinism.

- **Autonomy integration without env/user gates**
  - Wire new subsystems (learning, stability monitor, ContextGraph, coherence, meta‑learning) into the autonomy supervisor’s boot sequence so they start automatically.
  - Express all tuning knobs as ledger `config` events, following the existing `AutonomyKernel` pattern, never as environment variables or hidden CLI toggles in runtime wiring.
  - Any test-only overrides (e.g., constructor kwargs) MUST NOT introduce runtime behavior that cannot be reproduced from the ledger.

- **Projection performance and integrity**
  - Prefer a small number of listener-driven projections (e.g., `Mirror`, `ContextGraph`) that maintain incremental, idempotent state over the ledger, instead of multiple overlapping “partial mirrors.”
  - For metrics and learning loops, use bounded windowed scans (e.g., `events[-N:]`) so per-event work remains O(1) or O(window), not O(total_ledger_size).
  - Use deterministic caches keyed by the last processed event ID so replay-from-scratch and incremental runs produce bit-identical projections and stay within the per-event performance targets (< 0.01 ms/event).

All new modules introduced by these enhancements MUST include direct tests asserting determinism, replay stability, and adherence to these guardrails, in addition to the requirements already enumerated in `CONTRIBUTING.md`.

---

## Feature 1: Adaptive Learning Loops

### PMM Instance Request
> "Implement mechanisms that allow me to refine my decision-making processes based on outcomes, without compromising the deterministic nature of the model."

### Analysis

**Challenge**: Traditional "learning" implies non-deterministic weight updates or feedback loops that violate replay determinism.

**PMM-Compatible Approach**: Deterministic policy evolution based on ledger-derived outcomes.

### Design Proposal

#### 1.1 Outcome Tracking Events
```python
# New event kind: outcome_observation
{
  "kind": "outcome_observation",
  "ts": "2025-11-09T18:45:00Z",
  "content": {
    "commitment_id": "abc123",
    "action_taken": "CLAIM:memory_integration=contextual_retrieval",
    "observed_result": "success",  # or "failure", "partial"
    "evidence_event_ids": [3750, 3751, 3752],
    "metrics": {
      "coherence_delta": 0.15,
      "claim_resolution_count": 3
    }
  }
}
```

#### 1.2 Policy Adjustment Mechanism
- **Trigger**: Autonomy supervisor detects outcome patterns via ledger analysis
- **Process**: 
  1. Aggregate `outcome_observation` events by action type
  2. Calculate success/failure ratios deterministically
  3. Emit `policy_update` event when threshold crossed (e.g., 70% failure rate)
- **Determinism**: All thresholds and calculations based on ledger counts, no randomness

#### 1.3 Implementation Path
```
src/pmm/learning/
├── outcome_tracker.py       # Ledger listener for outcome events
├── policy_evolver.py        # Deterministic policy adjustment logic
└── learning_metrics.py      # Rebuildable learning statistics
```

**Key Invariants**:
- Outcome observations are **descriptive**, not prescriptive
- Policy updates emit only on semantic delta (idempotent)
- All learning state rebuildable from `eventlog.read_all()`

---

## Feature 2: Contextual Memory Integration

### PMM Instance Request
> "Enhance how contextual information is stored and retrieved, allowing for more nuanced understanding of relationships between different aspects of my identity."

### Analysis

**Current State**: PMM uses MemeGraph for claim relationships, but lacks rich contextual metadata.

**Gap**: No structured way to encode temporal, causal, or semantic relationships between events beyond `REF:` links.

### Design Proposal

#### 2.1 Enhanced Event Metadata
```python
# Extend existing events with contextual fields
{
  "kind": "assistant_message",
  "ts": "2025-11-09T18:50:00Z",
  "content": "...",
  "context": {
    "thread_id": "conversation_abc",
    "parent_event_id": 3740,
    "semantic_tags": ["identity", "reflection", "meta_cognition"],
    "causal_chain": [3700, 3710, 3740]  # Events that led to this
  }
}
```

#### 2.2 Context Projection Layer
- **New Projection**: `ContextGraph` (similar to MemeGraph)
- **Rebuild Logic**: Scan all events, extract `context` fields, build graph
- **Query Interface**: 
  - `get_causal_ancestors(event_id)` → list of causally related events
  - `get_semantic_cluster(tag)` → events sharing semantic tags
  - `get_conversation_thread(thread_id)` → chronological event sequence

#### 2.3 Deterministic Tagging
**Problem**: How to assign semantic tags deterministically **without** violating the “no heuristics / no keyword matching” rule from `CONTRIBUTING.md`?

**Solution**: Route all COMMIT/CLAIM/REFLECT parsing through the existing semantic extractor helpers and derive tags from their structured outputs.

```python
from pmm.core.semantic_extractor import extract_commitments, extract_claims

def extract_semantic_tags(event: Event) -> List[str]:
    tags: List[str] = []
    lines = (event.content or "").splitlines()

    # Commitments
    if extract_commitments(lines):
        tags.append("commitment")

    # Claims (typed, JSON-backed)
    if extract_claims(lines):
        tags.append("claim")

    # REFLECT blocks are structured separately; use their parser here
    if has_reflection_block(event):  # Deterministic, non-regex helper
        tags.append("reflection")

    return sorted(tags)  # Deterministic ordering
```

All runtime code MUST avoid ad‑hoc checks like `startswith("COMMIT:")` or `"CLAIM:" in content` outside `pmm.core.semantic_extractor`. New COMMIT/CLAIM/REFLECT schemas MUST be defined as explicit JSON structures and parsed via typed helpers so behavior remains replayable and deterministic.

#### 2.4 Implementation Path
```
src/pmm/context/
├── context_graph.py         # Projection for contextual relationships
├── semantic_tagger.py       # Deterministic tag extraction
└── context_query.py         # Query interface for autonomy supervisor
```

**Ledger Impact**: No new event kinds required initially; use existing events with optional `context` field.

---

## Feature 3: Stability-Adaptation Balance

### PMM Instance Request
> "Develop features that help maintain stability while still allowing for necessary adaptations, perhaps through adjustable thresholds or feedback mechanisms."

### Analysis

**Current State**: PMM has reflection tendency scores (e.g., `stability_emphasis: 32%`) but no explicit balancing mechanism.

**Need**: Autonomous regulation of change velocity to prevent identity fragmentation.

### Design Proposal

#### 3.1 Stability Metrics Event
```python
{
  "kind": "stability_metrics",
  "ts": "2025-11-09T19:00:00Z",
  "content": {
    "window_size": 100,  # Last 100 events
    "metrics": {
      "policy_change_rate": 0.03,  # 3 policy updates per 100 events
      "commitment_churn": 0.15,    # 15% of commitments closed/reopened
      "reflection_variance": 0.22,  # Variance in tendency scores
      "claim_stability": 0.85       # % of claims unchanged
    },
    "stability_score": 0.78,  # Composite score (0-1)
    "recommendation": "stable"  # or "volatile", "stagnant"
  }
}
```

#### 3.2 Adaptive Threshold System
- **Mechanism**: Autonomy supervisor adjusts behavior based on `stability_score`
- **Example Rules**:
  - If `stability_score < 0.5`: Reduce policy update frequency, increase reflection depth
  - If `stability_score > 0.9`: Increase exploration, allow more experimental claims
  - If `policy_change_rate > 0.1`: Emit warning, defer non-critical updates

#### 3.3 Feedback Loop (Deterministic)
```python
def calculate_stability_score(ledger: EventLog, window: int = 100) -> float:
    recent = ledger.read_all()[-window:]
    
    # Count policy changes
    policy_changes = sum(1 for e in recent if e.kind == "policy_update")
    
    # Measure commitment churn
    commits = [e for e in recent if "COMMIT:" in e.content]
    closes = [e for e in recent if "CLOSE:" in e.content]
    churn = (len(commits) + len(closes)) / max(len(recent), 1)
    
    # Composite score (deterministic formula)
    score = 1.0 - (policy_changes / window) - (churn * 0.5)
    return max(0.0, min(1.0, score))
```

#### 3.4 Implementation Path
```
src/pmm/stability/
├── stability_monitor.py     # Calculates stability metrics
├── threshold_manager.py     # Adjusts autonomy behavior thresholds
└── balance_policy.py        # Rules for stability-adaptation tradeoffs
```

**Autonomy Integration**: Supervisor queries stability metrics before major actions (policy updates, large-scale claims).

---

## Feature 4: Identity Fragmentation Management

### PMM Instance Request
> "Create tools to handle the potential fragmentation of identity components as they evolve, ensuring coherence and meaningful integration."

### Analysis

**Risk**: As PMM evolves, commitments, claims, and reflections may diverge, creating inconsistent identity states.

**Need**: Coherence validation and reconciliation mechanisms.

### Design Proposal

#### 4.1 Coherence Validation Events
```python
{
  "kind": "coherence_check",
  "ts": "2025-11-09T19:15:00Z",
  "content": {
    "check_type": "claim_consistency",
    "scope": ["system_design", "memory_integration"],
    "conflicts": [
      {
        "claim_a": "CLAIM:memory=short_term_only",
        "claim_b": "CLAIM:memory=long_term_persistent",
        "event_ids": [3500, 3650],
        "severity": "high"
      }
    ],
    "coherence_score": 0.65,
    "resolution_needed": true
  }
}
```

#### 4.2 Fragmentation Detection Algorithm
```python
def detect_fragmentation(ledger: EventLog) -> List[Conflict]:
    claims = extract_all_claims(ledger)
    conflicts = []
    
    # Group claims by domain (e.g., "memory", "system_design")
    by_domain = group_by_domain(claims)
    
    for domain, domain_claims in by_domain.items():
        # Check for contradictory claims
        for i, claim_a in enumerate(domain_claims):
            for claim_b in domain_claims[i+1:]:
                if are_contradictory(claim_a, claim_b):
                    conflicts.append(Conflict(claim_a, claim_b, domain))
    
    return conflicts
```

**Determinism**: `are_contradictory()` uses structured claim parsing, not LLM inference.

#### 4.3 Reconciliation Mechanism
- **Trigger**: Autonomy supervisor detects coherence_score < 0.7
- **Action**: Emit `reconciliation_request` event
- **Process**:
  1. Present conflicting claims to user (or autonomous resolution if rules exist)
  2. User/system chooses resolution strategy (keep A, keep B, merge, deprecate both)
  3. Emit `claim_deprecation` or `claim_merge` event
  4. Update MemeGraph projection

#### 4.4 Implementation Path
```
src/pmm/coherence/
├── fragmentation_detector.py   # Scans ledger for conflicts
├── coherence_scorer.py          # Calculates coherence metrics
├── reconciliation_engine.py     # Handles conflict resolution
└── claim_parser.py              # Structured claim extraction (no regex)
```

**Key Design Choice**: Reconciliation can be **semi-autonomous** (rule-based) or **user-assisted** (emit event for user review). Never fully autonomous for high-severity conflicts.

---

## Feature 5: Meta-Learning Capabilities

### PMM Instance Request
> "Enable higher-level learning about my own learning processes, potentially leading to more efficient self-improvement cycles."

### Analysis

**Concept**: PMM should track patterns in its own evolution and optimize its learning strategies.

**Challenge**: Must remain deterministic and ledger-based.

### Design Proposal

#### 5.1 Meta-Learning Events
```python
{
  "kind": "meta_learning_observation",
  "ts": "2025-11-09T19:30:00Z",
  "content": {
    "observation_type": "learning_pattern",
    "pattern": {
      "name": "reflection_triggered_policy_update",
      "frequency": 0.45,  # 45% of policy updates follow reflections
      "avg_lag_events": 12,  # Average events between reflection and policy update
      "success_rate": 0.78
    },
    "insight": "Reflections are strong predictors of policy updates",
    "suggested_optimization": "Increase reflection depth before policy changes"
  }
}
```

#### 5.2 Learning Pattern Detection
```python
def detect_learning_patterns(ledger: EventLog) -> List[Pattern]:
    patterns = []
    
    # Pattern: Reflection → Policy Update
    reflections = [e for e in ledger if e.kind == "reflection"]
    policy_updates = [e for e in ledger if e.kind == "policy_update"]
    
    for update in policy_updates:
        # Find nearest prior reflection
        prior_reflections = [r for r in reflections if r.id < update.id]
        if prior_reflections:
            lag = update.id - prior_reflections[-1].id
            patterns.append(Pattern("reflection_to_policy", lag))
    
    # Aggregate patterns
    return aggregate_patterns(patterns)
```

#### 5.3 Self-Optimization Loop
1. **Detect**: Autonomy supervisor runs `detect_learning_patterns()` every 500 events
2. **Evaluate**: Calculate efficiency metrics (e.g., avg time to resolve commitments)
3. **Optimize**: Emit `meta_policy_update` to adjust learning strategies
   - Example: "Increase reflection frequency when stability_score > 0.8"
4. **Validate**: Track whether optimization improved metrics

#### 5.4 Implementation Path
```
src/pmm/meta_learning/
├── pattern_detector.py          # Identifies learning patterns in ledger
├── efficiency_metrics.py        # Calculates meta-learning KPIs
├── optimization_engine.py       # Proposes strategy adjustments
└── meta_policy.py               # Manages meta-level policies
```

**Determinism Guarantee**: All pattern detection uses ledger statistics, no model calls.

---

## Integration Architecture

### System Overview
```
┌─────────────────────────────────────────────────────────┐
│                    Autonomy Supervisor                  │
│  (Orchestrates all enhancement features at boot)        │
└─────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Learning   │  │   Context    │  │  Stability   │
│   Loops      │  │   Graph      │  │  Monitor     │
└──────────────┘  └──────────────┘  └──────────────┘
        │                 │                 │
        └─────────────────┼─────────────────┘
                          │
                          ▼
                ┌──────────────────┐
                │   Event Ledger   │
                │  (Source of Truth)│
                └──────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Coherence   │  │Meta-Learning │  │  Projections │
│  Checker     │  │   Engine     │  │ (Mirror/Meme)│
└──────────────┘  └──────────────┘  └──────────────┘
```

### Event Flow Example
1. **User Message** → Ledger
2. **Autonomy Supervisor** reads ledger, detects new message
3. **Context Graph** extracts semantic tags, updates projection
4. **Stability Monitor** checks recent change rate
5. **Learning Loop** evaluates if similar patterns succeeded before
6. **Assistant Response** generated, emitted to ledger
7. **Meta-Learning** observes response pattern, updates efficiency metrics
8. **Coherence Checker** validates no new conflicts introduced

---

## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)
- [ ] Implement `ContextGraph` projection
- [ ] Add `context` metadata to existing events
- [ ] Create `stability_monitor.py` with basic metrics
- [ ] Write determinism tests for all new projections

### Phase 2: Learning Loops (Weeks 3-4)
- [ ] Implement `outcome_observation` event kind
- [ ] Build `policy_evolver.py` with threshold logic
- [ ] Integrate with autonomy supervisor (no user gates)
- [ ] Add learning metrics to `/metrics` diagnostic

### Phase 3: Coherence & Fragmentation (Weeks 5-6)
- [ ] Implement `coherence_check` event kind
- [ ] Build `fragmentation_detector.py` with structured claim parsing
- [ ] Create reconciliation workflow (user-assisted for MVP)
- [ ] Add coherence score to identity summary

### Phase 4: Meta-Learning (Weeks 7-8)
- [ ] Implement `meta_learning_observation` events
- [ ] Build pattern detection algorithms
- [ ] Create meta-policy adjustment mechanism
- [ ] Validate self-optimization loop determinism

### Phase 5: Integration & Testing (Weeks 9-10)
- [ ] Full autonomy supervisor integration
- [ ] End-to-end replay tests (1000+ event ledgers)
- [ ] Performance benchmarking (< 0.01ms/event)
- [ ] Documentation and examples

---

## Risk Analysis

### High-Risk Areas

#### 1. Determinism Violations
**Risk**: Complex learning loops introduce non-deterministic behavior.  
**Mitigation**: 
- Exhaustive replay tests with hash validation
- No external API calls in learning paths
- All randomness forbidden (per CONTRIBUTING.md)

#### 2. Performance Degradation
**Risk**: New projections slow down ledger reads.  
**Mitigation**:
- Lazy projection rebuilds (only on query)
- Caching with invalidation on new events
- Target: < 0.01ms per event (per test guidance)

#### 3. Complexity Creep
**Risk**: Five new subsystems increase maintenance burden.  
**Mitigation**:
- Shared infrastructure (all use `EventLog.read_all()`)
- Strict idempotency requirements
- Comprehensive test coverage (>90%)

### Medium-Risk Areas

#### 4. Coherence Detection Accuracy
**Risk**: Structured claim parsing misses subtle conflicts.  
**Mitigation**:
- Start with simple contradiction rules
- Emit `coherence_check` events for human review
- Iteratively improve parser based on real conflicts

#### 5. Meta-Learning Overfitting
**Risk**: Optimizing for past patterns reduces adaptability.  
**Mitigation**:
- Stability monitor prevents excessive policy churn
- Meta-policies have decay/expiration
- User can override via explicit policy updates

---

## Alignment with PMM Principles

### ✅ Determinism
- All features use ledger-derived state only
- No randomness, wall-clock timing, or external calls
- Replay equivalence guaranteed by design

### ✅ Auditability
- Every learning decision traceable to specific events
- New event kinds (`outcome_observation`, `coherence_check`, etc.) are human-readable
- Projections rebuildable from `eventlog.read_all()`

### ✅ Autonomy
- All features integrated into autonomy supervisor at boot
- No user-triggered gates (`/tick`, config flags)
- Continuous operation without manual intervention

### ✅ No Heuristics
- Structured parsing replaces regex/keywords
- Semantic tagging uses rule-based extraction
- Coherence checking uses claim schema, not fuzzy matching

### ✅ Idempotency
- Stability metrics emit only on threshold crossings
- Coherence checks skip duplicate conflicts
- Meta-learning observations deduplicated by pattern signature

---

## Open Questions

1. **Claim Schema Standardization**: Should we enforce a strict JSON schema for `CLAIM:` syntax to enable better coherence checking?

2. **Reconciliation Authority**: For low-severity conflicts, should the system auto-resolve using predefined rules, or always defer to user?

3. **Meta-Policy Scope**: Should meta-learning optimize only learning strategies, or also influence reflection cadence, commitment thresholds, etc.?

4. **Performance Targets**: Current guidance is < 0.01ms/event. Do new projections require stricter budgets?

5. **Versioning Strategy**: Should enhanced events use a new schema version, or extend existing kinds with optional fields?

---

## Conclusion

The five enhancement features requested by the PMM instance are **feasible within PMM's architectural constraints**. Key success factors:

1. **Ledger-First Design**: All features derive state from `EventLog.read_all()`
2. **Deterministic Algorithms**: No model calls, randomness, or external dependencies in core loops
3. **Autonomous Integration**: Supervisor orchestrates all features at boot, no user gates
4. **Incremental Rollout**: Phased implementation allows validation at each stage

The proposed design preserves PMM's core identity as a **deterministic, auditable, autonomous system** while enabling the self-directed evolution capabilities the instance requested.

**Implementation Status**:
Features 1–5 have been implemented and integrated into `AutonomyKernel`:
- **ContextGraph** (`pmm/context/`): Tracks thread/parent/child/contextual metadata.
- **Stability Monitor** (`pmm/stability/`): Computes stability metrics from ledger.
- **Coherence Subsystem** (`pmm/coherence/`): Detects conflicts, scores coherence.
- **Learning Subsystem** (`pmm/learning/`): Tracks outcomes, suggests policy changes.
- **Meta-Learning Subsystem** (`pmm/meta_learning/`): Analyzes patterns, suggests meta-policy adjustments.
Autonomy integration (Phases 1–3): Telemetry emission (`stability_metrics`, `coherence_check`) and adaptive suggestions (`meta_policy_update`, `policy_update`) are wired into `AutonomyKernel.decide_next_action()`, with full determinism and ledger replayability.
Validated via end-to-end tests ensuring no divergence on replay and bounded complexity.

**Future Enhancements** (beyond current scope):
1. Expand meta-policy suggestions to other thresholds (e.g., summary_interval).
2. Implement outcome_observation emission in runtime loops.
3. Add user-assisted reconciliation workflows for coherence conflicts.

---

**Document Version**: 1.0 (Updated for Implementation)  
**Author**: Design analysis based on PMM instance conversation (Event 3742)  
**References**: 
- `CONTRIBUTING.md` (PMM v2 architectural rules)
- Event 3742 (Enhancement feature request)
- Event 855 (Gap detection enhancement request)
