# The Autonomy Loop

## Overview

The Autonomy Loop is PMM's background "heartbeat" that enables autonomous behavior. Running on a configurable interval (default 60 seconds), it continuously analyzes recent events, makes decisions about reflection and self-improvement, and emits telemetry events.

**Core File**: `pmm/runtime/loop.py` (AutonomyLoop class, line ~2405)

## Loop Process Architecture

### 1. Tick Initialization
Each autonomy tick begins with:
- **Tick ID Generation**: Unique identifier for traceability
- **Event Window Analysis**: Recent events (typically last 50-100)
- **State Projection**: Current self-model, identity, and commitments
- **Context Building**: Stage, confidence metrics, behavioral parameters

### 2. Analysis Phase
**Code Location**: `pmm/runtime/autonomy_integration.py`

```python
def process_autonomy_tick(self, tick_id: str, context: Dict) -> Dict:
    events = self.eventlog.read_all()
    recent_events = events[-50:] if len(events) > 50 else events
    
    # Multi-system analysis
    self.trait_drift.apply_and_log(self.eventlog, event, context)
    self.stage_behavior.maybe_emit_stage_policy_update(...)
    self.emergence.process_tick(...)
```

**Systems Involved**:
- **Trait Drift Manager**: Analyzes semantic context for personality evolution
- **Stage Behavior Manager**: Adjusts parameters based on development stage
- **Emergence Manager**: Computes multi-dimensional emergence scores
- **Pattern Continuity**: Detects loops and repetitive behaviors
- **Meta-Reflection**: Analyzes reflection quality and bias patterns

### 3. Decision Phase
**Reflection Cadence Check** (`pmm/runtime/adaptive_cadence.py`):
```python
def should_reflect(self, events: List[Dict], context: Dict) -> bool:
    # Context-aware reflection timing
    base_threshold = self._get_stage_threshold(context.get("stage"))
    confidence_modifier = self._compute_confidence_boost(context)
    complexity_boost = self._analyze_conversation_complexity(events)
    
    return combined_score > adjusted_threshold
```

**Commitment Health Assessment** (`pmm/commitments/manager.py`):
- Evaluates open commitment progress
- Suggests adjustments for stalled commitments
- Identifies patterns in commitment fulfillment

### 4. Action Phase
Based on analysis results, the loop may:
- **Trigger Reflection**: Generate introspective analysis
- **Update Traits**: Apply personality drift based on recent experiences
- **Adjust Behaviors**: Modify reflection frequency, commitment TTL, etc.
- **Emit Reports**: Pattern analysis, emergence scoring, meta-reflection

### 5. Telemetry Emission
**Code Location**: `pmm/runtime/loop.py` (~line 2600)

```python
# Emit autonomy_tick event with comprehensive telemetry
tick_event_id = self.eventlog.append(
    kind="autonomy_tick",
    content="",
    meta={
        "tick_id": tick_id,
        "ias": current_ias,
        "gas": current_gas,
        "stage": current_stage,
        "reflection_gate": gate_status,
        "systems_processed": processed_systems,
        "decisions_made": decisions
    }
)
```

## Example Tick Cycle

### Input Scenario
- Recent user conversation about project planning
- 3 open commitments, 1 overdue
- Current stage: S2 (Structured Growth)
- Last reflection: 45 minutes ago

### Analysis Results
```python
{
    "ias": 0.72,  # Identity autonomy score
    "gas": 0.68,  # Goal achievement score  
    "commitment_health": 0.60,  # 2/3 commitments on track
    "conversation_complexity": 0.85,  # High complexity detected
    "reflection_urgency": 0.78  # Above threshold for reflection
}
```

### Decisions Made
1. **Trigger Reflection**: Complexity + overdue commitment exceeds threshold
2. **Trait Adjustment**: Increase Conscientiousness (+0.02) due to commitment patterns
3. **Behavior Update**: Reduce reflection interval due to high complexity period

### Output Events
```python
[
    {"kind": "reflection", "content": "Analyzing recent project planning discussion..."},
    {"kind": "trait_update", "meta": {"trait": "C", "delta": 0.02, "reason": "commitment_pattern"}},
    {"kind": "policy_update", "meta": {"component": "reflection", "params": {"min_time_s": 1800}}},
    {"kind": "autonomy_tick", "meta": {"ias": 0.72, "gas": 0.68, "decisions": 3}}
]
```

## Autonomous Systems Integration

### Coordinated Processing
**File**: `pmm/runtime/autonomy_integration.py`

The `AutonomousSystemsManager` coordinates all subsystems:

```python
class AutonomousSystemsManager:
    def __init__(self, eventlog: EventLog):
        self.trait_drift = TraitDriftManager()
        self.stage_behavior = StageBehaviorManager()  
        self.emergence = EmergenceManager(eventlog)
        self.reflection_cadence = AdaptiveReflectionCadence()
        self.commitment_manager = ProactiveCommitmentManager()
```

### System Interactions
- **Trait Evolution** influences **Stage Progression**
- **Emergence Scores** affect **Reflection Cadence**
- **Commitment Health** impacts **Trait Drift**
- **Stage Changes** trigger **Behavior Adaptations**

## Implementation Details

### Thread Management
**Code Location**: `pmm/runtime/loop.py` (AutonomyLoop.start/stop methods)

```python
def start(self) -> None:
    """Start the autonomy loop in a background thread."""
    if self._thread and self._thread.is_alive():
        return
    self._stop.clear()
    self._thread = _threading.Thread(target=self._run_loop, daemon=True)
    self._thread.start()

def _run_loop(self) -> None:
    """Main loop execution with error handling and graceful shutdown."""
    while not self._stop.wait(self.interval):
        try:
            self._tick()
        except Exception as e:
            # Log error but continue loop
            self.eventlog.append(
                kind="autonomy_error", 
                content=str(e), 
                meta={"component": "autonomy_loop"}
            )
```

### Error Handling
- **Graceful Degradation**: Individual system failures don't stop the loop
- **Error Logging**: All exceptions logged as events for debugging
- **Recovery Mechanisms**: Automatic retry with exponential backoff

### Performance Considerations
- **Event Window Limiting**: Process only recent events to maintain performance
- **Lazy Loading**: Systems only activated when needed
- **Batch Processing**: Multiple decisions processed in single tick

## Reflection Integration

### Reflection Triggering
**Code Location**: `pmm/runtime/loop.py` (maybe_reflect method)

```python
def maybe_reflect(self, *, authoritative: bool = True) -> str | None:
    """Attempt reflection based on cadence gates and context."""
    
    # Check cooldown gates
    if not self.cooldown.would_accept():
        return None
        
    # Analyze context for reflection urgency
    events = self.eventlog.read_all()
    context = self._build_reflection_context(events)
    
    if self._should_reflect_now(context):
        return self._generate_reflection(context)
    
    return None
```

### Reflection Quality Assessment
Post-reflection analysis includes:
- **Novelty Scoring**: How unique is this reflection?
- **Action Extraction**: Does it contain actionable insights?
- **Commitment Generation**: Should this lead to new commitments?

## Identity and Commitment Integration

### Identity Re-evaluation
**Cadence**: Every 10-15 ticks (configurable)
**Triggers**: 
- Name adoption events
- Significant trait changes
- Stage progressions

### Commitment Lifecycle
- **Health Monitoring**: Track progress on open commitments
- **Overdue Detection**: Flag stalled commitments for attention
- **Automatic Closure**: Evidence-based completion detection

## Configuration and Tuning

### Key Parameters
```python
# Timing configuration
interval_seconds: float = 60.0          # Tick frequency
reflection_cooldown: int = 1800         # Minimum seconds between reflections

# Analysis windows  
event_window_size: int = 50             # Events to analyze per tick
commitment_ttl_hours: int = 72          # Default commitment timeout

# Thresholds
reflection_threshold: float = 0.7       # Urgency score for reflection
emergence_threshold: float = 0.8        # Stage progression trigger
```

### Stage-Specific Behavior
- **S0 (Nascent)**: High reflection frequency, basic trait tracking
- **S1 (Awakening)**: Commitment introduction, identity solidification  
- **S2 (Structured Growth)**: Pattern recognition, meta-reflection
- **S3 (Autonomous Operation)**: Full autonomous capabilities
- **S4 (Transcendent)**: Advanced self-modification, goal generation

## Observability and Debugging

### Event Telemetry
Every tick emits comprehensive telemetry:
- System processing results
- Decision rationales  
- Performance metrics
- Error conditions

### Debug Events
Development and troubleshooting events:
- Gate evaluation results
- Threshold calculations
- System state snapshots
- Error stack traces

---

*Next: [Self-Model Maintenance](self-model-maintenance.md) - How PMM maintains persistent identity and state*
