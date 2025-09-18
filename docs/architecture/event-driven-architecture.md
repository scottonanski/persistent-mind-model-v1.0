# Event-Driven Architecture

## What "Event-First" Means in PMM

PMM is fundamentally **event-first**: every action, decision, and state change is recorded as an immutable event in an append-only log before any processing occurs. This architectural choice ensures complete auditability, deterministic behavior, and perfect reproducibility.

### Core Principles

- **Immutable History**: Events are never modified or deleted, only appended
- **Hash-Chained Integrity**: Each event is cryptographically linked to the previous one
- **State as Projection**: Current state is always reconstructed from event replay
- **Deterministic Processing**: Same event sequence always produces identical results

## Event Types and Code Mappings

### User/Assistant Messages
**Event Types**: `user_message`, `response`
**Code Location**: `pmm/runtime/loop.py`

```python
# User message handling (line ~1018)
rid = self.eventlog.append(
    kind="response", 
    content=reply, 
    meta={"source": "handle_user"}
)
```

**Flow**: User input → Runtime.handle_user() → EventLog.append() → Response generation

### Commitments
**Event Types**: `commitment_open`, `commitment_close`
**Code Location**: `pmm/commitments/tracker.py`

```python
# Commitment opening (tracker.py)
cid = self.eventlog.append(
    kind="commitment_open",
    content=commitment_text,
    meta={
        "cid": commitment_id,
        "source": "assistant_reply",
        "detector_confidence": confidence
    }
)
```

**Flow**: Assistant reply → CommitmentTracker.process_assistant_reply() → Event emission → Lifecycle tracking

### Trait Changes
**Event Types**: `trait_update`, `policy_update`
**Code Location**: `pmm/personality/self_evolution.py`, `pmm/runtime/stage_behaviors.py`

```python
# Trait evolution (self_evolution.py)
self.eventlog.append(
    kind="trait_update",
    content="",
    meta={
        "trait": trait_name,
        "delta": computed_delta,
        "reason": "semantic_drift",
        "source_event_id": source_eid
    }
)
```

**Flow**: Event analysis → TraitDriftManager.analyze_events() → Semantic analysis → Trait delta computation → Event emission

### Reflections
**Event Types**: `reflection`, `reflection_quality`, `reflection_action`
**Code Location**: `pmm/runtime/loop.py`

```python
# Reflection emission (loop.py ~1348)
rid_reflection = self.eventlog.append(
    kind="reflection",
    content=reflection_text,
    meta={
        "source": "autonomy_tick",
        "ias": current_ias,
        "gas": current_gas,
        "stage": current_stage
    }
)
```

**Flow**: Autonomy tick → Reflection cadence check → LLM reflection generation → Quality assessment → Event emission

### Stage Progressions
**Event Types**: `stage_update`, `emergence_report`
**Code Location**: `pmm/runtime/stage_tracker.py`, `pmm/runtime/emergence.py`

```python
# Stage progression (stage_tracker.py)
self.eventlog.append(
    kind="stage_update",
    content="",
    meta={
        "from_stage": old_stage,
        "to_stage": new_stage,
        "trigger": "emergence_threshold",
        "composite_score": score
    }
)
```

**Flow**: Emergence analysis → Stage evaluation → Threshold check → Stage transition → Behavioral parameter updates

## Event Flow Through the System

### 1. Event Creation
```
Input/Trigger → Component Logic → EventLog.append() → Database Storage
```

### 2. Hash Chain Validation
```python
# Hash chain implementation (eventlog.py ~192)
payload = {
    "id": eid,
    "ts": ts,
    "kind": kind,
    "content": content,
    "meta": meta_obj,
    "prev_hash": prev,
}
hash_bytes = _hashlib.sha256(self._canonical_json(payload)).digest()
hash_hex = hash_bytes.hex()
```

### 3. State Projection
```
Event Log → build_self_model() → Current State
Event Log → build_identity() → Identity State
```

### 4. Autonomous Processing
```
Event Window → Analysis → Decision → New Events → State Update
```

## Event Storage Implementation

### Database Schema
**File**: `pmm/storage/eventlog.py`

```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,           -- ISO8601 UTC timestamp
    kind TEXT NOT NULL,         -- Event type identifier
    content TEXT NOT NULL,      -- Event content/payload
    meta TEXT NOT NULL,         -- JSON metadata
    prev_hash TEXT,             -- Previous event hash (nullable for genesis)
    hash TEXT                   -- Current event hash (SHA-256)
);
```

### Hash Chain Integrity
- **Genesis Event**: `prev_hash = NULL`
- **Subsequent Events**: `prev_hash = previous_event.hash`
- **Tamper Detection**: Any modification breaks the chain
- **Verification**: Complete chain validation possible

## Conceptual Event Flow Diagram

```
[User Input] → [Runtime.handle_user()]
     ↓
[EventLog.append("response")] → [Hash Chain Update]
     ↓
[State Projection] → [Autonomous Processing]
     ↓
[Analysis Events] → [Decision Events] → [Action Events]
     ↓
[Updated Self-Model] → [Next Tick Cycle]
```

## Advanced Event Types

### Autonomous System Events
- `emergence_report`: Multi-dimensional scoring results
- `pattern_continuity_report`: Loop and repetition detection
- `meta_reflection_report`: Higher-order reflection analysis
- `semantic_growth_report`: Theme evolution tracking
- `directive_hierarchy_update`: Commitment organization

### Diagnostic Events
- `debug`: Development and troubleshooting information
- `audit_report`: System integrity checks
- `invariant_violation`: Constraint violation detection
- `embedding_indexed`: Semantic vector storage

### Integration Events
- `voice_continuity`: Model switching notifications
- `recall_suggest`: Memory retrieval recommendations
- `scene_compact`: Conversation summarization

## Event Metadata Standards

All events include standardized metadata:
- `component`: Originating system component
- `source_event_id`: Causal event reference (when applicable)
- `deterministic`: Boolean flag for reproducibility
- `digest`: Content hash for deduplication
- `timestamp`: Event creation time
- `stage`: Current development stage

## Auditability Features

### Complete Traceability
Every decision can be traced back through the event chain to its root cause.

### Reproducible Behavior
Given identical event sequences, PMM will make identical decisions.

### Rollback Capability
Any previous state can be reconstructed by replaying events up to a specific point.

### Integrity Verification
Hash chain validation ensures no events have been tampered with or corrupted.

---

*Next: [Autonomy Loop](autonomy-loop.md) - How PMM processes events autonomously*
