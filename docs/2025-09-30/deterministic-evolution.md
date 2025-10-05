# Deterministic Evolution

## Core Principle: Perfect Reproducibility

PMM's deterministic evolution ensures that given identical event sequences, the system will always make identical decisions and reach identical states. This fundamental property enables scientific study, debugging, and verification of AI behavior.

## Why Determinism Matters

### Traditional AI Problems
- **Black Box Decisions**: Impossible to trace why specific choices were made
- **Non-Reproducible Behavior**: Same inputs produce different outputs
- **Hidden State Dependencies**: Decisions influenced by invisible internal state
- **Debugging Impossibility**: Cannot reliably reproduce issues

### PMM's Deterministic Solution
- **Complete Traceability**: Every decision traces back to specific events
- **Perfect Reproducibility**: Identical event logs produce identical behavior
- **Transparent State**: All decision factors recorded in event log
- **Scientific Rigor**: Enables controlled experiments and validation

## Determinism Implementation

### 1. No Randomness Sources
**Code Enforcement**: `pmm/runtime/invariants.py`

```python
def check_invariants(events: List[Dict]) -> List[str]:
    """Validate deterministic behavior constraints."""
    violations = []
    
    # Check for non-deterministic dependencies
    for ev in events:
        meta = ev.get("meta", {})
        if "random_seed" in meta or "timestamp_dependency" in meta:
            violations.append("determinism:random_dependency")
```

**Prohibited Sources**:
- Random number generators
- System clock for decision logic (timestamps only for event ordering)
- External API calls for decision-making
- Non-deterministic hash functions
- Race conditions or threading dependencies

### 2. Evidence-Based Gating
**Principle**: All decisions must be based on concrete event evidence

**Code Location**: `pmm/personality/self_evolution.py`
```python
def apply_and_log(self, eventlog: EventLog, event: Dict, context: Dict) -> None:
    """Apply trait drift only when semantic evidence supports it."""
    
    # Extract semantic features deterministically
    semantic_features = self._extract_semantic_features(event.get("content", ""))
    
    # Only apply drift if evidence threshold met
    if semantic_features["confidence"] >= self.MIN_CONFIDENCE_THRESHOLD:
        trait_delta = self._compute_deterministic_delta(semantic_features)
        
        eventlog.append(
            kind="trait_update",
            content="",
            meta={
                "trait": trait_name,
                "delta": trait_delta,
                "evidence": semantic_features,
                "deterministic": True  # Flag for reproducibility
            }
        )
```

### 3. Deterministic Algorithms
**Semantic Analysis**: `pmm/runtime/semantic/semantic_growth.py`
```python
def analyze_texts(self, texts: List[str]) -> Dict[str, float]:
    """Deterministic keyword-based semantic analysis."""
    
    # Fixed keyword dictionaries ensure reproducibility
    theme_keywords = {
        "learning": ["learn", "study", "understand", "discover", ...],
        "creativity": ["create", "design", "build", "innovate", ...],
        # ... 8 total themes with 136 total keywords
    }
    
    # Word boundary matching prevents partial matches
    theme_counts = {}
    for theme, keywords in theme_keywords.items():
        count = sum(
            len(re.findall(rf'\b{re.escape(keyword)}\b', text.lower()))
            for text in texts
            for keyword in keywords
        )
        theme_counts[theme] = count
    
    return theme_counts
```

### 4. Digest-Based Deduplication
**Code Pattern**: Used across all autonomous systems

```python
def maybe_emit_report(self, analysis: Dict, context: Dict) -> Optional[int]:
    """Emit report only if content differs from previous reports."""
    
    # Create deterministic digest of report content
    report_content = {
        "analysis": analysis,
        "context": context,
        "timestamp": context.get("timestamp")  # For ordering only
    }
    
    digest = hashlib.sha256(
        json.dumps(report_content, sort_keys=True).encode()
    ).hexdigest()
    
    # Check if identical report already exists
    recent_events = self.eventlog.read_all()[-100:]
    for event in reversed(recent_events):
        if (event.get("kind") == "pattern_continuity_report" and
            event.get("meta", {}).get("digest") == digest):
            return None  # Skip duplicate
    
    # Emit new report with digest for future deduplication
    return self.eventlog.append(
        kind="pattern_continuity_report",
        content="",
        meta={
            "analysis": analysis,
            "digest": digest,
            "deterministic": True
        }
    )
```

## Reproducibility Examples

### Example 1: Trait Evolution Replay
```python
# Original event sequence
events = [
    {"id": 1, "kind": "user_message", "content": "Let's work on the creative project"},
    {"id": 2, "kind": "response", "content": "I'll help you brainstorm ideas"},
    {"id": 3, "kind": "trait_update", "meta": {"trait": "O", "delta": 0.02}}
]

# Replay produces identical results
model_1 = build_self_model(events)
model_2 = build_self_model(events)
assert model_1 == model_2  # Always true

# Trait values are identical
assert model_1["identity"]["traits"]["openness"] == 0.52
assert model_2["identity"]["traits"]["openness"] == 0.52
```

### Example 2: Stage Progression Determinism
```python
# Given identical IAS/GAS progression
events = generate_emergence_events(ias_sequence=[0.3, 0.4, 0.5, 0.6])

# Stage progression is always identical
stage_tracker_1 = StageTracker()
stage_tracker_2 = StageTracker()

for event in events:
    stage_1 = stage_tracker_1.process_event(event)
    stage_2 = stage_tracker_2.process_event(event)
    assert stage_1 == stage_2  # Deterministic progression
```

### Example 3: Reflection Content Determinism
```python
# Same context always produces same reflection decision
context = {
    "ias": 0.65,
    "gas": 0.58,
    "stage": "S2",
    "recent_events": [...],
    "commitment_health": 0.75
}

# Multiple reflection attempts with identical context
reflection_1 = reflection_cadence.should_reflect(context)
reflection_2 = reflection_cadence.should_reflect(context)
assert reflection_1 == reflection_2  # Always identical
```

## Auditability Mechanisms

### 1. Complete Event Traceability
**Code Location**: `pmm/storage/eventlog.py`

```python
def trace_decision_path(self, decision_event_id: int) -> List[Dict]:
    """Trace all events that influenced a specific decision."""
    
    events = self.read_all()
    decision_event = next(e for e in events if e["id"] == decision_event_id)
    
    # Extract causal event references
    source_event_id = decision_event.get("meta", {}).get("source_event_id")
    if not source_event_id:
        return [decision_event]
    
    # Recursively trace back to root causes
    causal_chain = []
    current_id = source_event_id
    
    while current_id:
        causal_event = next(e for e in events if e["id"] == current_id)
        causal_chain.append(causal_event)
        current_id = causal_event.get("meta", {}).get("source_event_id")
    
    return causal_chain + [decision_event]
```

### 2. Hash Chain Integrity
**Tamper Detection**: Any modification breaks the cryptographic chain

```python
def verify_integrity(self) -> bool:
    """Verify complete event log integrity."""
    events = self.read_all()
    
    for i, event in enumerate(events):
        if i == 0:
            # Genesis event has no previous hash
            if event.get("prev_hash") is not None:
                return False
        else:
            # Each event must reference previous event's hash
            prev_event = events[i-1]
            if event.get("prev_hash") != prev_event.get("hash"):
                return False
            
            # Verify current event's hash is correct
            computed_hash = self._compute_event_hash(event)
            if event.get("hash") != computed_hash:
                return False
    
    return True
```

### 3. Rollback Capability
**Point-in-Time Recovery**: Reconstruct any previous state

```python
def rollback_to_event(self, target_event_id: int) -> Dict:
    """Reconstruct system state at specific point in time."""
    
    events = self.read_all()
    events_subset = [e for e in events if e["id"] <= target_event_id]
    
    # Rebuild complete state from event subset
    identity = build_identity(events_subset)
    self_model = build_self_model(events_subset)
    commitments = build_commitment_state(events_subset)
    
    return {
        "identity": identity,
        "self_model": self_model,
        "commitments": commitments,
        "event_count": len(events_subset),
        "rollback_point": target_event_id
    }
```

## Invariant Enforcement

### System Invariants
**Code Location**: `pmm/runtime/invariants.py`

```python
def check_invariants(events: List[Dict]) -> List[str]:
    """Validate system-wide consistency constraints."""
    violations = []
    
    # 1. Ledger shape integrity
    violations.extend(check_ledger_shape(events))
    
    # 2. Identity consistency (no silent reversions)
    violations.extend(check_identity_invariants(events))
    
    # 3. Trait bounds enforcement [0.0, 1.0]
    violations.extend(check_trait_bounds(events))
    
    # 4. Commitment lifecycle integrity
    violations.extend(check_commitment_invariants(events))
    
    # 5. Stage progression validity
    violations.extend(check_stage_invariants(events))
    
    return violations
```

### Automatic Violation Handling
```python
def handle_invariant_violations(self, violations: List[str]) -> None:
    """Automatically correct or log invariant violations."""
    
    for violation in violations:
        if violation.startswith("trait_bounds:"):
            self._correct_trait_bounds()
        elif violation.startswith("identity:"):
            self._log_identity_inconsistency(violation)
        elif violation.startswith("commitment:"):
            self._repair_commitment_state(violation)
        else:
            # Log unknown violations for manual review
            self.eventlog.append(
                kind="invariant_violation",
                content=violation,
                meta={"severity": "unknown", "auto_correctable": False}
            )
```

## Scientific Validation

### Controlled Experiments
```python
def run_determinism_test(event_sequence: List[Dict], iterations: int = 100):
    """Validate deterministic behavior across multiple runs."""
    
    results = []
    for i in range(iterations):
        # Fresh system instance for each run
        eventlog = EventLog(path=f":memory:{i}")
        runtime = Runtime(eventlog=eventlog)
        
        # Apply identical event sequence
        for event in event_sequence:
            runtime.process_event(event)
        
        # Capture final state
        final_state = runtime.get_complete_state()
        results.append(final_state)
    
    # Verify all results are identical
    first_result = results[0]
    for i, result in enumerate(results[1:], 1):
        assert result == first_result, f"Run {i} differs from run 0"
    
    return True  # All runs produced identical results
```

### Regression Testing
```python
def test_behavioral_regression():
    """Ensure system behavior doesn't change between versions."""
    
    # Load canonical test scenarios
    test_scenarios = load_canonical_scenarios()
    
    for scenario in test_scenarios:
        # Run scenario with current implementation
        current_result = run_scenario(scenario["events"])
        
        # Compare with expected result
        expected_result = scenario["expected_state"]
        
        assert current_result == expected_result, (
            f"Behavioral regression detected in scenario {scenario['name']}"
        )
```

## Development Guidelines

### Deterministic Code Patterns
1. **Use fixed dictionaries** instead of dynamic collections
2. **Sort all iterations** to ensure consistent ordering
3. **Avoid system time** in decision logic (use event timestamps)
4. **Hash content deterministically** with sorted keys
5. **Validate inputs** to prevent non-deterministic edge cases

### Testing Determinism
```python
def test_deterministic_function():
    """Template for testing deterministic behavior."""
    
    # Test identical inputs produce identical outputs
    input_data = {...}
    result_1 = function_under_test(input_data)
    result_2 = function_under_test(input_data)
    assert result_1 == result_2
    
    # Test across multiple runs
    results = [function_under_test(input_data) for _ in range(10)]
    assert all(r == results[0] for r in results)
    
    # Test serialization stability
    serialized = json.dumps(result_1, sort_keys=True)
    deserialized = json.loads(serialized)
    result_3 = function_under_test(input_data)
    assert result_3 == deserialized
```

---

*This completes the core architecture documentation. See [Table of Contents](../README.md) for navigation to implementation guides and API references.*
