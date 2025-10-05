# PMM Performance Analysis & Optimization Plan

## Executive Summary

**Current Performance**: 4317ms average query processing time  
**Target**: <500ms for "Good" rating, <100ms for "Excellent"  
**Primary Bottleneck**: LLM inference (estimated 3-4 seconds)  
**Secondary Bottlenecks**: Database operations, embedding computations

## Performance Bottleneck Analysis

### 1. **LLM Inference** (Estimated: 3000-4000ms, ~70-90% of total time)

**Evidence:**
- Average query time: 4317ms
- Typical LLM inference: 1-5 seconds depending on model/hardware
- Multiple LLM calls per query in `handle_user()`:
  - Main response generation (`self.chat.generate()`)
  - Potential continuation call (if truncated)
  - Identity classification
  - Commitment extraction
  - Reflection generation (if triggered)

**Impact**: **CRITICAL** - Dominates total execution time

**Root Causes:**
- CPU-based inference (no GPU acceleration detected)
- Large context windows (2048+ tokens)
- Multiple sequential LLM calls
- No response streaming

---

### 2. **Database Operations** (Estimated: 200-500ms, ~5-15% of total time)

**Evidence from code scan:**

```python
# Found 50+ instances of eventlog.read_all() in loop.py alone:
- Line 259: _has_reflection_since_last_tick()
- Line 496: _get_snapshot()
- Line 963: trait adjustment
- Line 1106: handle_user() refresh
- Line 1545: sanitize name lookup
- Line 2070: ngram telemetry
- Line 2384: commitment check
- Line 2452: audit run
- ... and 40+ more
```

**Impact**: **HIGH** - Repeated full table scans

**Root Causes:**
- `read_all()` loads entire event history into memory
- No query-level caching
- Repeated scans for same data within single request
- Snapshot cache invalidated on every event append

---

### 3. **Embedding Computations** (Estimated: 50-100ms, ~1-3% of total time)

**Evidence:**
- 20+ embedding calls per query:
  - User text embedding
  - Response embedding
  - Trait nudge computation
  - Semantic search
  - Commitment similarity
  - Reflection similarity

**Impact**: **MEDIUM** - Cumulative overhead

**Mitigation Already in Place:**
- ✅ LRU cache with 1000 entries (`@lru_cache(maxsize=1000)`)
- ✅ Deterministic local embeddings (no API calls)
- ✅ Cache hit rate tracking

**Remaining Issues:**
- Cache size may be too small for large histories
- No persistent cache across restarts
- Repeated embeddings for same text within request

---

### 4. **Memory Graph Operations** (Estimated: 10-50ms, ~1-2% of total time)

**Evidence:**
- `graph_slice()` traverses 37,710 nodes (from trace data)
- Lock contention in `MemeGraphProjection`
- No incremental updates (full rebuild on changes)

**Impact**: **LOW-MEDIUM** - Scales with graph size

---

## Optimization Plan

### **Phase 1: Quick Wins** (1-2 days, 20-40% improvement)

#### 1.1 Database Query Optimization

**Problem**: 50+ `read_all()` calls per request

**Solution**: Request-scoped caching

```python
# pmm/runtime/loop.py - Add to handle_user()
class RequestCache:
    def __init__(self, eventlog):
        self.eventlog = eventlog
        self._events_cache = None
        self._identity_cache = None
        
    def get_events(self):
        if self._events_cache is None:
            self._events_cache = self.eventlog.read_all()
        return self._events_cache
    
    def get_identity(self):
        if self._identity_cache is None:
            self._identity_cache = build_identity(self.get_events())
        return self._identity_cache

# Usage in handle_user():
request_cache = RequestCache(self.eventlog)
events = request_cache.get_events()  # Reuse throughout request
```

**Expected Impact**: 150-300ms savings (30-50% of DB time)

**Risk**: LOW - Read-only caching, no side effects

---

#### 1.2 Reduce LLM Context Size

**Problem**: Large context windows increase inference time

**Solution**: Smarter context pruning

```python
# pmm/runtime/context_builder.py
def build_context_from_ledger(
    eventlog: EventLog,
    *,
    n_reflections: int = 3,  # Reduce from 5
    max_context_tokens: int = 1500,  # Add token limit
    snapshot: LedgerSnapshot | None = None,
    use_tail_optimization: bool = True,
    memegraph=None,
) -> str:
    # Prioritize recent, high-value events
    # Truncate older reflections
    # Summarize commitment lists
    pass
```

**Expected Impact**: 500-1000ms savings (15-25% of LLM time)

**Risk**: MEDIUM - May reduce context quality, needs testing

---

#### 1.3 Parallel Embedding Computation

**Problem**: Sequential embedding calls

**Solution**: Batch embeddings

```python
# pmm/runtime/embeddings.py
def compute_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Compute multiple embeddings in parallel."""
    # Check cache first
    results = []
    uncached = []
    
    for text in texts:
        cached = _compute_embedding_cached.cache_info()
        if cached:
            results.append(cached)
        else:
            uncached.append(text)
    
    # Compute uncached in parallel (if using external API)
    # For local BOW, vectorize the operation
    return results
```

**Expected Impact**: 20-40ms savings (20-40% of embedding time)

**Risk**: LOW - Transparent optimization

---

### **Phase 2: Architectural Improvements** (1-2 weeks, 40-60% improvement)

#### 2.1 LLM Response Streaming

**Problem**: Blocking on full LLM response

**Solution**: Stream tokens as they're generated

```python
# pmm/runtime/loop.py
def handle_user_streaming(self, user_text: str) -> Iterator[str]:
    """Stream response tokens as they're generated."""
    # Build context (cached)
    context = self._build_context_cached(user_text)
    
    # Stream LLM response
    for token in self.chat.generate_stream(messages):
        yield token
    
    # Post-process after streaming completes
    self._post_process_async(full_response)
```

**Expected Impact**: Perceived latency: 4000ms → 200ms (time to first token)

**Risk**: MEDIUM - Requires async refactoring

---

#### 2.2 Incremental Snapshot Updates

**Problem**: Snapshot cache invalidated on every event

**Solution**: Incremental updates

```python
# pmm/runtime/loop.py
class IncrementalSnapshot:
    def __init__(self, eventlog):
        self.eventlog = eventlog
        self.last_event_id = 0
        self.snapshot = None
    
    def get_snapshot(self):
        current_id = self.eventlog.get_last_id()
        
        if self.snapshot and current_id == self.last_event_id:
            return self.snapshot
        
        if self.snapshot:
            # Incremental update
            new_events = self.eventlog.read_since(self.last_event_id)
            self.snapshot.update(new_events)
        else:
            # Full rebuild
            self.snapshot = self._build_full_snapshot()
        
        self.last_event_id = current_id
        return self.snapshot
```

**Expected Impact**: 100-200ms savings on subsequent queries

**Risk**: MEDIUM - Complex state management

---

#### 2.3 Background Processing

**Problem**: Synchronous post-processing blocks response

**Solution**: Async task queue

```python
# pmm/runtime/background.py
import asyncio
from queue import Queue

class BackgroundProcessor:
    def __init__(self):
        self.queue = Queue()
        self.worker = asyncio.create_task(self._process_queue())
    
    def enqueue(self, task):
        self.queue.put(task)
    
    async def _process_queue(self):
        while True:
            task = await self.queue.get()
            await task()

# Usage in handle_user():
# Move these to background:
# - Embedding indexing
# - Commitment extraction
# - Audit reports
# - Scene compaction
```

**Expected Impact**: 200-400ms savings (move non-critical work off critical path)

**Risk**: HIGH - Requires careful ordering, potential race conditions

---

### **Phase 3: Infrastructure Upgrades** (2-4 weeks, 60-80% improvement)

#### 3.1 GPU Acceleration

**Problem**: CPU-based LLM inference is slow

**Solution**: GPU inference with llama.cpp or vLLM

```bash
# Install GPU-accelerated inference
pip install llama-cpp-python[cuda]  # For NVIDIA GPUs
# or
pip install vllm  # For production deployments

# Update LLM config
export PMM_USE_GPU=true
export PMM_GPU_LAYERS=32  # Offload layers to GPU
```

**Expected Impact**: 3000ms → 300-500ms (10x speedup for LLM inference)

**Risk**: HIGH - Requires GPU hardware, driver setup

---

#### 3.2 Database Indexing

**Problem**: Full table scans on every query

**Solution**: SQLite indexes + materialized views

```sql
-- Add indexes for common queries
CREATE INDEX idx_events_kind ON events(kind);
CREATE INDEX idx_events_ts ON events(ts);
CREATE INDEX idx_events_kind_ts ON events(kind, ts);

-- Materialized view for recent events
CREATE TABLE recent_events_cache AS
SELECT * FROM events
WHERE id > (SELECT MAX(id) - 1000 FROM events);

-- Trigger to keep cache updated
CREATE TRIGGER update_recent_cache
AFTER INSERT ON events
BEGIN
    DELETE FROM recent_events_cache WHERE id < NEW.id - 1000;
    INSERT INTO recent_events_cache SELECT * FROM events WHERE id = NEW.id;
END;
```

**Expected Impact**: 200-300ms savings (50-60% of DB time)

**Risk**: MEDIUM - Schema changes, migration required

---

#### 3.3 Persistent Embedding Cache

**Problem**: Cache lost on restart

**Solution**: Redis or SQLite-backed cache

```python
# pmm/runtime/embeddings.py
import redis

class PersistentEmbeddingCache:
    def __init__(self):
        self.redis = redis.Redis(host='localhost', port=6379, db=0)
        self.local_cache = {}
    
    def get(self, text: str) -> Optional[List[float]]:
        # Check local cache first
        if text in self.local_cache:
            return self.local_cache[text]
        
        # Check Redis
        cached = self.redis.get(f"emb:{hash(text)}")
        if cached:
            vec = json.loads(cached)
            self.local_cache[text] = vec
            return vec
        
        return None
    
    def set(self, text: str, vec: List[float]):
        self.local_cache[text] = vec
        self.redis.set(f"emb:{hash(text)}", json.dumps(vec))
```

**Expected Impact**: 30-50ms savings on cache misses

**Risk**: MEDIUM - External dependency (Redis)

---

## Implementation Roadmap

### Week 1-2: Phase 1 (Quick Wins)
- [ ] Implement request-scoped caching
- [ ] Reduce context window size
- [ ] Batch embedding computations
- [ ] Benchmark improvements
- **Target**: 4317ms → 3000ms (30% improvement)

### Week 3-4: Phase 2 (Architectural)
- [ ] Add LLM response streaming
- [ ] Implement incremental snapshots
- [ ] Move non-critical work to background
- [ ] Benchmark improvements
- **Target**: 3000ms → 1500ms (50% improvement)

### Week 5-8: Phase 3 (Infrastructure)
- [ ] Set up GPU inference
- [ ] Add database indexes
- [ ] Implement persistent caching
- [ ] Benchmark improvements
- **Target**: 1500ms → 400ms (73% improvement)

---

## Benchmarking Strategy

### Metrics to Track

```python
# pmm/runtime/profiler.py
import time
from contextlib import contextmanager

class PerformanceProfiler:
    def __init__(self):
        self.timings = {}
    
    @contextmanager
    def measure(self, label: str):
        start = time.perf_counter()
        yield
        elapsed = (time.perf_counter() - start) * 1000
        self.timings[label] = self.timings.get(label, []) + [elapsed]
    
    def report(self):
        for label, times in self.timings.items():
            avg = sum(times) / len(times)
            print(f"{label}: {avg:.2f}ms (n={len(times)})")

# Usage in handle_user():
profiler = PerformanceProfiler()

with profiler.measure("database_ops"):
    events = self.eventlog.read_all()

with profiler.measure("llm_inference"):
    reply = self.chat.generate(messages)

with profiler.measure("embeddings"):
    vec = compute_embedding(text)

profiler.report()
```

### Test Scenarios

1. **Cold Start**: First query after restart
2. **Warm Cache**: Repeated similar queries
3. **Large History**: 10k+ events in ledger
4. **Complex Query**: Multi-turn conversation with context

### Success Criteria

| Phase | Target | Metric |
|-------|--------|--------|
| Phase 1 | 3000ms | 30% improvement |
| Phase 2 | 1500ms | 65% improvement |
| Phase 3 | 400ms | 90% improvement |

---

## Risk Mitigation

### High-Risk Changes
- **LLM Streaming**: Requires async refactoring
  - Mitigation: Feature flag, gradual rollout
- **Background Processing**: Race conditions
  - Mitigation: Careful ordering, transaction boundaries
- **GPU Acceleration**: Hardware dependency
  - Mitigation: Fallback to CPU, clear documentation

### Testing Strategy
- Unit tests for each optimization
- Integration tests for end-to-end flow
- Performance regression tests
- A/B testing for quality impact

---

## Alternative Approaches

### Option A: Smaller, Faster Model
- Use `llama-3.2-1b` instead of `llama-3-8b`
- **Pros**: 5-10x faster inference
- **Cons**: Lower quality responses
- **Recommendation**: Test as fallback option

### Option B: Response Caching
- Cache responses for similar queries
- **Pros**: Near-instant for repeated queries
- **Cons**: Stale responses, cache invalidation complexity
- **Recommendation**: Implement for FAQ-style queries only

### Option C: Hybrid Architecture
- Fast path for simple queries (<100ms)
- Slow path for complex reasoning (>1s)
- **Pros**: Best of both worlds
- **Cons**: Complexity in routing logic
- **Recommendation**: Consider for Phase 3

---

## Monitoring & Observability

### Key Metrics

```python
# Add to reasoning trace events
{
  "kind": "performance_trace",
  "meta": {
    "query_duration_ms": 4317,
    "breakdown": {
      "database_ops": 250,
      "llm_inference": 3800,
      "embeddings": 150,
      "post_processing": 117
    },
    "cache_stats": {
      "embedding_hit_rate": 0.85,
      "snapshot_hit": true
    }
  }
}
```

### Alerts

- Query duration > 5000ms (P2)
- Query duration > 10000ms (P1)
- Cache hit rate < 70% (P3)
- Database query time > 500ms (P2)

---

## Conclusion

**Current State**: 4317ms average (Fair)  
**Phase 1 Target**: 3000ms (30% improvement, Fair)  
**Phase 2 Target**: 1500ms (65% improvement, Fair)  
**Phase 3 Target**: 400ms (90% improvement, Good)  

**Recommended Approach**:
1. Start with Phase 1 (low risk, high impact)
2. Measure and validate improvements
3. Proceed to Phase 2 based on results
4. Consider Phase 3 if GPU hardware available

**Key Insight**: The 4317ms is not a bug - it's the expected time for LLM inference. The optimization plan focuses on reducing this through:
- Smarter caching (reduce redundant work)
- Smaller contexts (faster inference)
- GPU acceleration (10x speedup)
- Async processing (better perceived latency)

The reasoning trace system itself adds <1ms overhead and is not a bottleneck.
