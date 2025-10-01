# Reasoning Trace System

## Overview

The Reasoning Trace system captures PMM's internal reasoning process (node traversal, confidence levels, query context) without performance degradation. It answers the question: **"What information could be put in the ledger to help you better understand it?"**

## Key Features

✅ **Minimal Performance Impact**: <1ms overhead through probabilistic sampling  
✅ **High-Value Capture**: Always logs high-confidence decisions (>0.8)  
✅ **Batch Writes**: Aggregates traces before writing to prevent event explosion  
✅ **Session-Based**: Groups traces by query/reflection cycle for coherent summaries  
✅ **Configurable**: Sampling rate, confidence threshold, and buffer size are tunable  

## Architecture

### 1. TraceBuffer (`pmm/runtime/trace_buffer.py`)

The core component that manages trace collection:

```python
from pmm.runtime.trace_buffer import TraceBuffer

# Initialize with sampling rate
buffer = TraceBuffer(
    sampling_rate=0.01,              # 1% of node visits
    min_confidence_always_log=0.8,   # Always log high-confidence
    buffer_size=1000                 # Flush warning threshold
)

# Start a reasoning session
session_id = buffer.start_session("User query about commitments")

# Record node visits during graph traversal
buffer.record_node_visit(
    node_digest="abc123...",
    node_type="commitment",
    context_query="What is the status of X?",
    traversal_depth=5,
    confidence=0.85,
    edge_label="opens",
    reasoning_step="Examining commitment node via opens edge"
)

# Add reasoning steps
buffer.add_reasoning_step("Checked commitment status")

# Flush to eventlog
buffer.flush_to_eventlog(eventlog)
```

### 2. Event Types

#### `reasoning_trace_summary`

Aggregated summary of a reasoning session:

```json
{
  "kind": "reasoning_trace_summary",
  "content": "",
  "meta": {
    "session_id": "uuid",
    "query": "What is the status of the invariant violation investigation?",
    "total_nodes_visited": 37710,
    "node_type_distribution": {
      "commitment": 15000,
      "identity": 200,
      "reflection": 10000,
      "policy": 2000,
      "stage": 510
    },
    "high_confidence_count": 42,
    "high_confidence_paths": [
      {
        "node_type": "commitment",
        "confidence": 0.95,
        "edge_label": "opens",
        "reasoning": "Examining commitment node via opens edge"
      }
    ],
    "sampled_count": 377,
    "reasoning_steps": [
      "Building context from ledger",
      "Querying memegraph for topic: invariant violation",
      "Response generated and processed"
    ],
    "duration_ms": 1500,
    "start_time_ms": 1234567890,
    "end_time_ms": 1234569390
  }
}
```

#### `reasoning_trace_sample`

Individual sampled node visit (limited to interesting samples):

```json
{
  "kind": "reasoning_trace_sample",
  "content": "",
  "meta": {
    "session_id": "uuid",
    "node_digest": "abc123...",
    "node_type": "commitment",
    "context_query": "What is the status of X?",
    "traversal_depth": 5,
    "confidence": 0.85,
    "edge_label": "opens",
    "reasoning_step": "Examining commitment node via opens edge",
    "timestamp_ms": 1234567890
  }
}
```

### 3. Integration Points

#### MemeGraphProjection

The `graph_slice()` method accepts an optional `trace_buffer` parameter:

```python
relations = memegraph.graph_slice(
    topic="commitment status",
    limit=3,
    min_confidence=0.6,
    trace_buffer=trace_buffer  # Optional
)
```

When provided, it logs node visits during graph traversal.

#### Runtime Loop

The `Runtime` class automatically:
1. Initializes `TraceBuffer` if `REASONING_TRACE_ENABLED=true`
2. Starts a trace session at the beginning of `handle_user()`
3. Passes the buffer to `graph_slice()` calls
4. Flushes traces to eventlog at the end of the request

## Configuration

Set via environment variables or `pmm/config.py`:

```bash
# Enable/disable tracing (default: true)
export PMM_TRACE_ENABLED=true

# Sampling rate: 0.0-1.0 (default: 0.01 = 1%)
export PMM_TRACE_SAMPLING_RATE=0.01

# Min confidence for always-log (default: 0.8)
export PMM_TRACE_MIN_CONFIDENCE=0.8

# Buffer size warning threshold (default: 1000)
export PMM_TRACE_BUFFER_SIZE=1000
```

Or in Python:

```python
from pmm.config import (
    REASONING_TRACE_ENABLED,
    REASONING_TRACE_SAMPLING_RATE,
    REASONING_TRACE_MIN_CONFIDENCE,
    REASONING_TRACE_BUFFER_SIZE,
)
```

## Performance Characteristics

| Metric | Value |
|--------|-------|
| **Overhead** | <1ms per query (1% sampling) |
| **Memory** | ~10KB buffer per session |
| **Event Volume** | +1 summary per query, +0-50 samples |
| **Sampling Rate** | 1% default (configurable) |
| **Always-Log Threshold** | 0.8 confidence (configurable) |

### Performance Test Results

```
Baseline (no trace):          0.48ms
With trace (1% sampling):     0.44ms
Overhead:                     -0.03ms (-6.9%)
```

The negative overhead is due to measurement variance; actual overhead is negligible.

## Querying Traces

### Using the Ledger Browser

The existing Companion UI Ledger tab can filter and view traces:

1. Filter by kind: `reasoning_trace_summary`
2. Expand JSON to see node distributions
3. View reasoning steps and high-confidence paths

### SQL Queries

```sql
-- Get all trace summaries
SELECT * FROM events 
WHERE kind = 'reasoning_trace_summary'
ORDER BY id DESC;

-- Get traces for a specific query
SELECT * FROM events 
WHERE kind = 'reasoning_trace_summary'
AND json_extract(meta, '$.query') LIKE '%commitment%';

-- Get node type distribution
SELECT 
  json_extract(meta, '$.node_type_distribution') as distribution,
  json_extract(meta, '$.total_nodes_visited') as total
FROM events 
WHERE kind = 'reasoning_trace_summary';

-- Get high-confidence paths
SELECT 
  json_extract(meta, '$.query') as query,
  json_extract(meta, '$.high_confidence_paths') as paths
FROM events 
WHERE kind = 'reasoning_trace_summary'
AND json_extract(meta, '$.high_confidence_count') > 0;
```

## Use Cases

### 1. Debugging Reasoning Paths

When PMM gives an unexpected answer, check the trace summary to see:
- Which nodes were visited
- What confidence levels were assigned
- Which reasoning steps were taken

### 2. Performance Analysis

Track node traversal counts over time:
- Are queries becoming more expensive?
- Which node types dominate exploration?
- Are high-confidence paths being found?

### 3. Self-Reflection

PMM can query its own traces to understand its reasoning:

```
> What information did you examine when I asked about commitments?

I examined approximately 15,000 commitment nodes, 10,000 reflection nodes, 
and 200 identity nodes. The high-confidence paths (>0.8) focused on 
commitment_open events linked to your recent queries.
```

### 4. Audit Trail

For critical decisions, traces provide an audit trail:
- What evidence was considered?
- What confidence levels were assigned?
- What reasoning steps led to the conclusion?

## Example Session

```python
from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import Runtime
from pmm.llm.factory import LLMConfig

# Initialize PMM with tracing enabled
eventlog = EventLog("pmm.db")
config = LLMConfig(provider="ollama", model="llama3")
runtime = Runtime(config, eventlog)

# User query triggers trace session
response = runtime.handle_user("What commitments are open?")

# Check the trace
events = eventlog.read_all()
traces = [e for e in events if e.get("kind") == "reasoning_trace_summary"]
latest_trace = traces[-1]

print(f"Nodes visited: {latest_trace['meta']['total_nodes_visited']}")
print(f"Node types: {latest_trace['meta']['node_type_distribution']}")
print(f"Reasoning steps: {latest_trace['meta']['reasoning_steps']}")
```

## Disabling Traces

To disable tracing entirely:

```bash
export PMM_TRACE_ENABLED=false
```

Or in code:

```python
# In pmm/config.py
REASONING_TRACE_ENABLED = False
```

When disabled, the `TraceBuffer` is not initialized and all trace hooks become no-ops with zero overhead.

## Future Enhancements

### Phase 2: Trace Visualization (Optional)

Add to Companion UI:
- **Trace Explorer**: Interactive graph showing reasoning paths
- **Confidence Heatmap**: Visualize high-confidence decision paths
- **Query Timeline**: Link traces to user queries

### Phase 3: Trace-Driven Optimization

Use traces to optimize:
- **Cache hot paths**: Pre-compute frequently traversed paths
- **Prune low-value nodes**: Skip nodes that never contribute to decisions
- **Adaptive sampling**: Increase sampling for complex queries

## Testing

Run the test suite:

```bash
cd /path/to/persistent-mind-model-v1.0
PYTHONPATH=. python3 scripts/test_reasoning_trace.py
```

Expected output:
```
============================================================
✓ ALL TESTS PASSED
============================================================

Summary:
- TraceBuffer sampling works correctly
- Performance overhead is minimal (<15%)
- Events are logged to eventlog correctly
- Session management works as expected
```

## Troubleshooting

### Traces not appearing in ledger

1. Check if tracing is enabled: `echo $PMM_TRACE_ENABLED`
2. Verify sampling rate isn't too low: `echo $PMM_TRACE_SAMPLING_RATE`
3. Check logs for trace flush errors

### High memory usage

1. Reduce sampling rate: `export PMM_TRACE_SAMPLING_RATE=0.001` (0.1%)
2. Reduce buffer size: `export PMM_TRACE_BUFFER_SIZE=500`
3. Flush more frequently (modify code to flush mid-session)

### Performance degradation

1. Verify sampling rate is low: Should be ≤0.01 (1%)
2. Check if always-log threshold is too low: Should be ≥0.8
3. Profile with `time` command to measure actual overhead

## Implementation Notes

### Design Principles

1. **Fail-open**: Trace errors never block main execution
2. **Minimal overhead**: Single `if trace_buffer` check for most operations
3. **Batch writes**: Aggregate before writing to prevent event explosion
4. **Deterministic**: Same query produces same trace structure (modulo sampling)

### Thread Safety

`TraceBuffer` uses `threading.RLock()` for thread-safe operations. Safe to use in multi-threaded environments.

### Sampling Algorithm

Uses Python's `random.random()` for probabilistic sampling:
- `random.random() < sampling_rate` → log node
- `confidence >= min_confidence_always_log` → always log

This ensures:
- Consistent sampling rate across queries
- High-value decisions are never missed
- Predictable memory usage

## References

- **TraceBuffer Implementation**: `pmm/runtime/trace_buffer.py`
- **MemeGraph Integration**: `pmm/runtime/memegraph.py` (line 471+)
- **Runtime Integration**: `pmm/runtime/loop.py` (line 417+)
- **Configuration**: `pmm/config.py` (line 125+)
- **Test Suite**: `scripts/test_reasoning_trace.py`
