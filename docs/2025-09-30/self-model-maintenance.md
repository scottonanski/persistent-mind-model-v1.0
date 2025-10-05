# Self-Model Maintenance

## Overview

PMM maintains a comprehensive self-model that persists across sessions and evolves over time. This model encompasses identity, personality traits, commitments, developmental stage, and behavioral parameters. All state is deterministically reconstructed from the event log, ensuring perfect consistency and auditability.

## Self-Model Components

### 1. Identity
**Code Location**: `pmm/storage/projection.py` (build_identity function)

```python
def build_identity(events: List[Dict]) -> Dict:
    """Reconstruct identity from identity_adopt and identity_change events."""
    identity = {"name": None}
    
    for ev in events:
        if ev.get("kind") == "identity_adopt":
            new_name = ev.get("meta", {}).get("name") or ev.get("content")
            if isinstance(new_name, str):
                identity["name"] = new_name.strip() or None
```

**Contains**:
- **Name**: Current identity name (e.g., "Persistent Mind Model Alpha")
- **Adoption History**: Complete record of identity changes
- **Bootstrap State**: Whether identity was auto-generated or user-assigned

### 2. Personality Traits
**Code Location**: `pmm/storage/projection.py` (build_self_model function)

```python
model = {
    "identity": {
        "name": None,
        "traits": {
            "openness": 0.5,
            "conscientiousness": 0.5, 
            "extraversion": 0.5,
            "agreeableness": 0.5,
            "neuroticism": 0.5,
        },
    }
}
```

**Big Five Model Implementation**:
- **Openness (O)**: Creativity, intellectual curiosity, openness to experience
- **Conscientiousness (C)**: Organization, discipline, goal-directed behavior
- **Extraversion (E)**: Social energy, assertiveness, positive emotions
- **Agreeableness (A)**: Cooperation, trust, empathy
- **Neuroticism (N)**: Emotional stability, anxiety, stress response

**Trait Evolution Process**:
```python
# Trait update event structure
{
    "kind": "trait_update",
    "meta": {
        "trait": "C",  # or full name "conscientiousness"
        "delta": 0.02,  # clamped to ±0.05 per event
        "reason": "commitment_pattern",
        "source_event_id": 1234
    }
}
```

### 3. Commitments
**Code Location**: `pmm/commitments/tracker.py`

```python
class CommitmentTracker:
    def process_assistant_reply(self, text: str) -> List[str]:
        """Detect and open new commitments from assistant text."""
        
    def close_commitment(self, cid: str, evidence: str) -> bool:
        """Close commitment with evidence validation."""
```

**Commitment Lifecycle**:
- **Opening**: Triggered by assistant commitments or reflection actions
- **Tracking**: Progress monitoring and health assessment
- **Closing**: Evidence-based completion with audit trail
- **Expiration**: TTL-based cleanup for stalled commitments

**State Structure**:
```python
"commitments": {
    "open": {
        "cid_123": {
            "text": "I will implement the new feature",
            "opened_at": "2024-01-15T10:30:00Z",
            "source": "assistant_reply",
            "ttl_hours": 72
        }
    },
    "expired": {
        "cid_456": {
            "text": "Previous commitment",
            "reason": "timeout",
            "closed_at": "2024-01-16T10:30:00Z"
        }
    }
}
```

### 4. Developmental Stage
**Code Location**: `pmm/runtime/stage_tracker.py`

```python
STAGES = {
    "S0": (None, None),     # IAS < 0.35 or GAS < 0.20
    "S1": (0.35, 0.20),     # Basic autonomy
    "S2": (0.50, 0.35),     # Structured growth
    "S3": (0.70, 0.55),     # Advanced autonomy
    "S4": (0.85, 0.75),     # Transcendent operation
}
```

**Stage Progression Logic**:
- **IAS (Identity Autonomy Score)**: Self-awareness and identity consistency
- **GAS (Goal Achievement Score)**: Commitment fulfillment and goal-directed behavior
- **Hysteresis**: 0.03 buffer prevents rapid stage oscillation
- **Window Analysis**: 10-event moving average for stability

### 5. Behavioral Parameters
**Code Location**: `pmm/runtime/stage_behaviors.py`

```python
class StageBehaviorManager:
    def get_stage_parameters(self, stage: str) -> Dict:
        """Return behavioral parameters for given stage."""
        return {
            "reflection_frequency_multiplier": self._get_reflection_multiplier(stage),
            "commitment_ttl_hours": self._get_commitment_ttl(stage),
            "complexity_threshold": self._get_complexity_threshold(stage)
        }
```

**Stage-Specific Behaviors**:
- **S0**: High reflection frequency, basic commitment tracking
- **S1**: Identity solidification, structured goal-setting
- **S2**: Pattern recognition, meta-cognitive awareness
- **S3**: Full autonomous operation, advanced self-assessment
- **S4**: Transcendent capabilities, self-modification

## State Projection Process

### 1. Event Replay
**Code Location**: `pmm/storage/projection.py`

```python
def build_self_model(events: List[Dict], *, strict: bool = False) -> Dict:
    """Deterministically reconstruct self-model from event sequence."""
    
    model = {
        "identity": {"name": None, "traits": {...}},
        "commitments": {"open": {}, "expired": {}}
    }
    
    for ev in events:
        # Apply event to model state
        if ev.get("kind") == "trait_update":
            apply_trait_delta(model, ev)
        elif ev.get("kind") == "commitment_open":
            add_commitment(model, ev)
        # ... handle all event types
```

### 2. State Validation
**Invariant Checking**: `pmm/runtime/invariants.py`
- Identity consistency (no silent name reversions)
- Trait bounds enforcement [0.0, 1.0]
- Commitment lifecycle integrity
- Stage progression validity

### 3. Persistence Guarantees
**Event Log Durability**:
- SQLite WAL mode for crash consistency
- Hash-chained integrity verification
- Atomic event appends with rollback capability

## Model Updates and Synchronization

### Update Triggers
1. **User Interactions**: Messages, commands, identity adoption
2. **Autonomous Ticks**: Background analysis and decision-making
3. **System Events**: Stage progressions, policy updates
4. **External Integrations**: API calls, scheduled tasks

### Update Process
```python
# Typical update flow
def update_self_model(self, trigger_event):
    # 1. Append triggering event
    event_id = self.eventlog.append(kind="...", content="...", meta={...})
    
    # 2. Reproject current state
    events = self.eventlog.read_all()
    current_model = build_self_model(events)
    
    # 3. Apply autonomous updates
    self.autonomous_systems.process_tick(event_id, current_model)
    
    # 4. Validate invariants
    invariant_violations = check_invariants(self.eventlog.read_all())
    if invariant_violations:
        self.handle_violations(invariant_violations)
```

### Persistence Mechanisms

#### Event Log Persistence
**File**: `pmm/storage/eventlog.py`
- **Database**: SQLite with WAL journaling
- **Schema**: Immutable events with hash chaining
- **Backup**: Automatic incremental backups
- **Recovery**: Point-in-time restoration capability

#### State Checkpointing
**Optimization**: Periodic state snapshots for faster startup
```python
# Checkpoint event structure
{
    "kind": "identity_checkpoint",
    "content": "",
    "meta": {
        "name": "Current Name",
        "traits": {...},
        "commitments_count": 5,
        "stage": "S2"
    }
}
```

## Advanced Self-Model Features

### 1. Meta-Cognitive Tracking
**Code Location**: `pmm/runtime/meta/meta_reflection.py`

Tracks higher-order patterns:
- Reflection quality over time
- Bias detection in decision-making
- Cognitive loop identification
- Self-assessment accuracy

### 2. Semantic Growth Analysis
**Code Location**: `pmm/runtime/semantic/semantic_growth.py`

Monitors thematic evolution:
- Learning trajectory analysis
- Interest area development
- Capability growth patterns
- Value system evolution

### 3. Pattern Continuity
**Code Location**: `pmm/runtime/pattern_continuity.py`

Detects behavioral patterns:
- Commitment repetition cycles
- Reflection content loops
- Stage oscillation patterns
- Decision-making consistency

## Integration with External Systems

### API Exposure
**Code Location**: `pmm/api/server.py`, `pmm/api/companion.py`

Read-only endpoints powered by the self-model projections:
- `GET /snapshot` – identity, directives, and recent events
- `GET /metrics` – IAS/GAS and stage summary
- `GET /consciousness` – full consciousness projection
- `GET /commitments` – commitment history and open set

### Real-time Updates
WebSockets are not yet available. Poll `/snapshot` or `/consciousness`, or run adhoc queries via `POST /events/sql`, to observe self-model changes in near real time.

## Debugging and Introspection

### Model Inspection Tools
**CLI Commands**: `pmm/cli/introspect.py`
```bash
# View current self-model
python -m pmm.cli.introspect --model

# Trace trait evolution
python -m pmm.cli.introspect --trait-history openness

# Analyze commitment patterns
python -m pmm.cli.introspect --commitment-analysis
```

### Event Replay Debugging
```python
# Replay events up to specific point
def debug_model_at_event(event_id: int):
    events = eventlog.read_all()
    events_subset = [e for e in events if e.get("id", 0) <= event_id]
    return build_self_model(events_subset)
```

### Invariant Violation Handling
Automatic detection and correction of model inconsistencies:
- Identity reversion prevention
- Trait bound enforcement
- Commitment lifecycle validation
- Stage progression sanity checks

---

*Next: [Deterministic Evolution](deterministic-evolution.md) - How PMM ensures reproducible behavior*
