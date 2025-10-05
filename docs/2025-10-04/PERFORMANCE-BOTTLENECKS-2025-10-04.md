# Performance Bottlenecks Analysis - Post Refactor

**Date**: 2025-10-04  
**Context**: After massive refactor of `loop.py` (6,701 → 4,595 LOC) and `tracker.py` (~1,200 LOC)  
**Issue**: Performance is now worse than before the refactor

## Executive Summary

**Root Cause**: Excessive `read_all()` calls throughout the codebase (134 total calls identified).

**Critical Hotspots**:
1. `AutonomyLoop.tick()` - **17 read_all() calls** in a single method
2. `AutonomyLoop.handle_identity_adopt()` - **10 read_all() calls**
3. `CommitmentTracker._rebind_commitments_on_identity_adopt()` - **6 read_all() calls**
4. `emit_reflection()` - **5 read_all() calls**
5. `maybe_reflect()` - **5 read_all() calls**

**Impact**: Each `read_all()` call reads the entire event log from SQLite. With a growing event log, this becomes O(n) per operation, compounding to O(n²) or worse for operations with multiple calls.

---

## Detailed Analysis

### 1. Top Offenders by File

| File | read_all() Calls | Primary Functions |
|------|------------------|-------------------|
| `runtime/loop.py` | **44** | `tick()` (17), `handle_identity_adopt()` (10) |
| `commitments/tracker.py` | **26** | `_rebind_commitments_on_identity_adopt()` (6), `close_with_evidence()` (3) |
| `runtime/loop/reflection.py` | **11** | `emit_reflection()` (5), `maybe_reflect()` (5) |
| `runtime/autonomy_integration.py` | 4 | `process_autonomy_tick()` (2) |
| `runtime/loop/assessment.py` | 4 | Various assessment functions |

**Total**: 134 `read_all()` calls across runtime and commitments modules.

### 2. Critical Functions with Multiple Calls

These functions call `read_all()` multiple times within a single execution:

1. **`AutonomyLoop.tick()` - 17 calls**
   - Lines: 2998, 3041, 3094, 3120, 3415, 3580, 3599, 3625, 3771, 3989, 3998, 4187, 4280, 4418, 4491, 4555, 4557
   - **Impact**: Every autonomy tick (every 10 seconds) reads the entire log 17 times
   - **Estimated overhead**: 17× database reads per tick

2. **`AutonomyLoop.handle_identity_adopt()` - 10 calls**
   - Lines: 2141, 2197, 2321, 2356, 2370, 2384, 2405, 2435, 2453, 2483
   - **Impact**: Identity adoption triggers 10 full log scans
   - **Estimated overhead**: 10× database reads per identity change

3. **`CommitmentTracker._rebind_commitments_on_identity_adopt()` - 6 calls**
   - Lines: 156, 158, 220, 222, 244, 246
   - **Impact**: Commitment rebinding on identity change reads log 6 times
   - **Estimated overhead**: 6× database reads per rebind operation

4. **`emit_reflection()` - 5 calls**
   - Lines: 55, 185, 214, 247, 341
   - **Impact**: Every reflection emission reads the entire log 5 times
   - **Estimated overhead**: 5× database reads per reflection

5. **`maybe_reflect()` - 5 calls**
   - Lines: 404, 419, 493, 518, 538
   - **Impact**: Reflection gating logic reads log 5 times
   - **Estimated overhead**: 5× database reads per reflection check

### 3. Why This Happened During Refactor

The refactor extracted functions into separate modules (`reflection.py`, `handlers.py`, `assessment.py`, etc.). Each extracted function now independently calls `read_all()` instead of receiving events as parameters.

**Before refactor** (monolithic):
```python
def tick(self):
    events = self.eventlog.read_all()  # Once
    # ... use events throughout method
    self._do_something(events)
    self._do_another_thing(events)
```

**After refactor** (modular):
```python
def tick(self):
    self._do_something()  # Calls read_all() internally
    self._do_another_thing()  # Calls read_all() internally
    # ... 15 more function calls, each calling read_all()
```

---

## Performance Impact Estimation

Assuming:
- Event log size: 1,000 events (typical after a few sessions)
- `read_all()` cost: ~5ms (SQLite read + deserialization)
- Autonomy tick frequency: Every 10 seconds

**Per autonomy tick**:
- 17 `read_all()` calls in `tick()`
- 5 `read_all()` calls in `maybe_reflect()` (called from tick)
- 5 `read_all()` calls in `emit_reflection()` (if reflection triggered)
- **Total**: 27+ `read_all()` calls per tick

**Overhead**: 27 × 5ms = **135ms per tick** just for database reads

**With 10,000 events** (after extended use):
- `read_all()` cost: ~50ms
- **Overhead**: 27 × 50ms = **1,350ms (1.35 seconds) per tick**

This explains why performance degrades significantly as the event log grows.

---

## Optimization Recommendations

### Priority 1: Immediate Fixes (High Impact, Low Effort)

#### 1.1 Pass Events as Parameters

**Target**: `tick()`, `handle_identity_adopt()`, reflection functions

**Change**:
```python
# Before
def tick(self):
    events = self.eventlog.read_all()  # Call 1
    self._do_something()  # Calls read_all() internally (Call 2)
    self._do_another_thing()  # Calls read_all() internally (Call 3)

# After
def tick(self):
    events = self.eventlog.read_all()  # Call 1 only
    self._do_something(events)
    self._do_another_thing(events)
```

**Impact**: Reduce `tick()` from 17 calls to 1 call (94% reduction)

**Files to modify**:
- `pmm/runtime/loop.py::AutonomyLoop.tick()`
- `pmm/runtime/loop.py::AutonomyLoop.handle_identity_adopt()`
- `pmm/runtime/loop/reflection.py::emit_reflection()`
- `pmm/runtime/loop/reflection.py::maybe_reflect()`
- `pmm/commitments/tracker.py::CommitmentTracker._rebind_commitments_on_identity_adopt()`

#### 1.2 Use Snapshot Cache

**Target**: Functions that need full projection (identity, self_model, stage)

**Change**:
```python
# Before
def some_function(self):
    events = self.eventlog.read_all()
    identity = build_identity(events)
    self_model = build_self_model(events)

# After
def some_function(self):
    snapshot = self._get_snapshot()  # Cached until new event
    identity = snapshot.identity
    self_model = snapshot.self_model
```

**Impact**: Eliminate redundant projection rebuilds

**Files to modify**:
- `pmm/runtime/loop.py` (multiple functions)
- `pmm/commitments/tracker.py` (projection-dependent functions)

#### 1.3 Use read_tail() for Recent Data

**Target**: Functions that only need recent events (last 100-500)

**Change**:
```python
# Before
def check_recent_reflections(self):
    events = self.eventlog.read_all()  # Reads 10,000 events
    recent = events[-100:]  # Only uses last 100

# After
def check_recent_reflections(self):
    recent = self.eventlog.read_tail(limit=100)  # Reads 100 events
```

**Impact**: 100× reduction in data read for recent-only operations

**Files to modify**:
- `pmm/runtime/loop/reflection.py` (reflection checks)
- `pmm/runtime/loop/assessment.py` (assessment windows)
- `pmm/commitments/tracker.py` (idempotency checks)

### Priority 2: Architectural Improvements (High Impact, Medium Effort)

#### 2.1 Request-Scoped Event Cache

**Concept**: Cache `read_all()` results for the duration of a single operation (e.g., one tick, one user turn).

**Implementation**:
```python
class RequestScopedCache:
    def __init__(self, eventlog):
        self._eventlog = eventlog
        self._cache = None
        self._last_id = None
    
    def get_events(self):
        current_id = self._eventlog.get_max_id()
        if self._cache is None or current_id != self._last_id:
            self._cache = self._eventlog.read_all()
            self._last_id = current_id
        return self._cache
    
    def invalidate(self):
        self._cache = None
```

**Usage**:
```python
def tick(self):
    cache = RequestScopedCache(self.eventlog)
    events = cache.get_events()  # First call: reads from DB
    
    self._do_something(cache)  # Uses cache
    self._do_another_thing(cache)  # Uses cache
    # ... all subsequent calls use cache
```

**Impact**: Reduce N calls to 1 call per operation

**Files to create**:
- `pmm/runtime/request_cache.py` (already exists, needs integration)

**Files to modify**:
- `pmm/runtime/loop.py::AutonomyLoop.tick()`
- `pmm/runtime/loop.py::Runtime.handle_user()`

#### 2.2 Incremental Projection Updates

**Concept**: Instead of rebuilding projections from scratch on every `read_all()`, maintain incremental state.

**Implementation**: Use `pmm/storage/projection_cache.py` (already exists)

**Impact**: Reduce projection rebuild cost from O(n) to O(1) for new events

**Files to modify**:
- `pmm/runtime/loop.py::Runtime._get_snapshot()` (integrate projection_cache)
- `pmm/storage/projection.py` (add incremental update support)

#### 2.3 Lazy Projection Loading

**Concept**: Don't build full projections unless actually needed.

**Implementation**:
```python
class LazySnapshot:
    def __init__(self, events):
        self._events = events
        self._identity = None
        self._self_model = None
    
    @property
    def identity(self):
        if self._identity is None:
            self._identity = build_identity(self._events)
        return self._identity
    
    @property
    def self_model(self):
        if self._self_model is None:
            self._self_model = build_self_model(self._events)
        return self._self_model
```

**Impact**: Avoid expensive projections when not needed

### Priority 3: Database Optimizations (Medium Impact, Low Effort)

#### 3.1 Add Composite Indexes

**Target**: Queries that filter by kind + id

**SQL**:
```sql
CREATE INDEX IF NOT EXISTS idx_events_kind_id ON events(kind, id);
CREATE INDEX IF NOT EXISTS idx_events_ts_kind ON events(ts, kind);
```

**Impact**: 5-10× speedup for filtered queries

**Files to modify**:
- `pmm/storage/eventlog.py::EventLog.__init__()` (add indexes)

#### 3.2 Use read_after_id() for Incremental Reads

**Target**: Operations that process new events since last check

**Change**:
```python
# Before
def process_new_events(self):
    all_events = self.eventlog.read_all()
    new_events = [e for e in all_events if e['id'] > self.last_processed_id]

# After
def process_new_events(self):
    new_events = self.eventlog.read_after_id(self.last_processed_id)
```

**Impact**: Read only new events, not entire log

---

## Implementation Plan

### Phase 1: Quick Wins (1-2 hours)

1. **Modify `AutonomyLoop.tick()`**
   - Call `read_all()` once at the start
   - Pass `events` to all helper functions
   - **Expected reduction**: 17 calls → 1 call

2. **Modify `handle_identity_adopt()`**
   - Call `read_all()` once at the start
   - Pass `events` to all helper functions
   - **Expected reduction**: 10 calls → 1 call

3. **Modify reflection functions**
   - Add `events` parameter to `emit_reflection()` and `maybe_reflect()`
   - **Expected reduction**: 10 calls → 0 calls (receive events from caller)

**Total impact**: ~37 calls eliminated (~28% reduction)

### Phase 2: Caching Layer (2-4 hours)

1. **Integrate RequestScopedCache**
   - Wrap eventlog in cache for tick operations
   - Wrap eventlog in cache for user turns
   - **Expected reduction**: Remaining calls → 1 call per operation

2. **Use snapshot cache consistently**
   - Replace `read_all()` + projection with `_get_snapshot()`
   - **Expected reduction**: Eliminate redundant projections

**Total impact**: ~70 calls eliminated (~52% reduction)

### Phase 3: Architectural Improvements (4-8 hours)

1. **Incremental projection updates**
2. **Lazy projection loading**
3. **Database index optimization**

**Total impact**: Further 2-5× speedup on remaining operations

---

## Validation Plan

### Before Optimization

Run baseline performance test:
```bash
python3 scripts/profile_performance.py > baseline_perf.txt
```

### After Each Phase

1. Run performance test
2. Compare `read_all()` call count
3. Compare operation timings
4. Run full test suite to ensure no regressions

### Success Criteria

- [ ] `read_all()` calls reduced by >80% (134 → <27)
- [ ] Autonomy tick overhead <50ms (vs current 135ms+)
- [ ] User turn latency <200ms (vs current 500ms+)
- [ ] All tests passing (707 passed, 4 skipped)
- [ ] No behavior changes (deterministic replay preserved)

---

## Risk Assessment

### Low Risk
- Passing events as parameters (pure refactor, no behavior change)
- Using `read_tail()` for recent data (equivalent results)
- Database indexes (transparent optimization)

### Medium Risk
- Request-scoped caching (must invalidate correctly)
- Snapshot cache integration (must handle cache invalidation)

### High Risk
- Incremental projection updates (complex state management)
- Lazy loading (potential race conditions)

**Recommendation**: Start with Phase 1 (low risk, high impact), validate thoroughly, then proceed to Phase 2.

---

## Monitoring

After optimization, add performance monitoring:

1. **Log read_all() call counts** per operation
2. **Track operation timings** (tick, user turn, reflection)
3. **Monitor event log growth** vs performance degradation
4. **Alert on slow operations** (>1 second)

**Implementation**: Use `pmm/runtime/profiler.py` (already exists)

---

## Conclusion

The performance degradation is **not** due to the refactor itself, but rather due to **unintended duplication of database reads** when extracting functions into separate modules.

**Root cause**: Functions that previously shared a single `read_all()` call now each call it independently.

**Solution**: Pass events as parameters or use request-scoped caching.

**Expected improvement**: 5-10× speedup after Phase 1+2 optimizations.

**Next steps**: 
1. Review this document with the team
2. Implement Phase 1 optimizations
3. Validate with performance tests
4. Proceed to Phase 2 if needed
