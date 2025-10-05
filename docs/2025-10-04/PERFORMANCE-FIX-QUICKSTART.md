# Performance Fix Quick Start Guide

**Problem**: Performance degraded after refactor due to excessive `read_all()` calls (134 total).

**Solution**: Implement Phase 1 optimizations (pass events as parameters).

---

## Quick Diagnosis

Run this to see the problem:
```bash
python3 scripts/analyze_read_all_hotspots.py
```

**Key findings**:
- `AutonomyLoop.tick()`: **17 read_all() calls** (lines 2998-4557)
- `handle_identity_adopt()`: **10 read_all() calls** (lines 2141-2483)
- `emit_reflection()`: **5 read_all() calls** (lines 55-341 in reflection.py)
- `maybe_reflect()`: **5 read_all() calls** (lines 404-538 in reflection.py)

---

## Phase 1: Critical Fixes (1-2 hours, 80% improvement)

### Fix 1: AutonomyLoop.tick() - Eliminate 16 of 17 calls

**Current pattern** (repeated 17 times):
```python
def tick(self):
    # ... some code ...
    events = self.eventlog.read_all()  # Call #1
    # ... use events ...
    
    # ... more code ...
    events2 = self.eventlog.read_all()  # Call #2
    # ... use events2 ...
    
    # ... repeated 15 more times ...
```

**Fixed pattern**:
```python
def tick(self):
    # Read once at the start
    events = self.eventlog.read_all()
    
    # Pass events to all operations
    # ... use events throughout ...
    
    # For operations that need fresh events after appends:
    # Only re-read if we've appended new events
    if self._events_appended_this_tick:
        events = self.eventlog.read_all()
```

**Lines to modify**: 2998, 3041, 3094, 3120, 3415, 3580, 3599, 3625, 3771, 3989, 3998, 4187, 4280, 4418, 4491, 4555, 4557

**Strategy**:
1. Add `events = self.eventlog.read_all()` at line ~2950 (start of tick method)
2. Replace each subsequent `self.eventlog.read_all()` with `events`
3. Track when new events are appended, re-read only if needed

### Fix 2: handle_identity_adopt() - Eliminate 9 of 10 calls

**Current pattern**:
```python
def handle_identity_adopt(self, name: str):
    events1 = self.eventlog.read_all()  # Call #1
    # ... check something ...
    
    events2 = self.eventlog.read_all()  # Call #2
    # ... check something else ...
    
    # ... repeated 8 more times ...
```

**Fixed pattern**:
```python
def handle_identity_adopt(self, name: str):
    events = self.eventlog.read_all()  # Call #1 only
    
    # Pass events to all checks
    # ... use events throughout ...
```

**Lines to modify**: 2141, 2197, 2321, 2356, 2370, 2384, 2405, 2435, 2453, 2483

### Fix 3: Reflection Functions - Eliminate 10 calls

**File**: `pmm/runtime/loop/reflection.py`

**Change function signatures**:
```python
# Before
def emit_reflection(runtime, ...):
    events = runtime.eventlog.read_all()  # Call #1
    # ...
    events2 = runtime.eventlog.read_all()  # Call #2
    # ...

def maybe_reflect(runtime, ...):
    events = runtime.eventlog.read_all()  # Call #1
    # ...

# After
def emit_reflection(runtime, events, ...):
    # Use passed events parameter
    # ...

def maybe_reflect(runtime, events, ...):
    # Use passed events parameter
    # ...
```

**Caller changes** (in `loop.py`):
```python
# Before
emit_reflection(self, ...)
maybe_reflect(self, ...)

# After
events = self.eventlog.read_all()  # Or use existing events variable
emit_reflection(self, events, ...)
maybe_reflect(self, events, ...)
```

### Fix 4: CommitmentTracker Functions - Eliminate 6 calls

**File**: `pmm/commitments/tracker.py`

**Function**: `_rebind_commitments_on_identity_adopt()`

**Lines**: 156, 158, 220, 222, 244, 246

**Change**:
```python
# Before
def _rebind_commitments_on_identity_adopt(self, old_name, new_name, ...):
    events1 = self.eventlog.read_all()
    # ...
    events2 = self.eventlog.read_all()
    # ...

# After
def _rebind_commitments_on_identity_adopt(self, old_name, new_name, ..., events=None):
    if events is None:
        events = self.eventlog.read_all()
    # Use events throughout
```

---

## Phase 2: Caching Layer (2-4 hours, additional 50% improvement)

### Option A: Request-Scoped Cache (Recommended)

**Create**: `pmm/runtime/event_cache.py`

```python
class EventCache:
    """Cache events for the duration of a single operation."""
    
    def __init__(self, eventlog):
        self.eventlog = eventlog
        self._cache = None
        self._last_max_id = None
    
    def get_events(self):
        """Get events, using cache if valid."""
        current_max = self.eventlog.get_max_id()
        if self._cache is None or current_max != self._last_max_id:
            self._cache = self.eventlog.read_all()
            self._last_max_id = current_max
        return self._cache
    
    def invalidate(self):
        """Invalidate cache after appending events."""
        self._cache = None
        self._last_max_id = None
```

**Usage in tick()**:
```python
def tick(self):
    cache = EventCache(self.eventlog)
    events = cache.get_events()  # First call: reads from DB
    
    # All subsequent reads use cache
    self._do_something(cache)  # Internally calls cache.get_events()
    self._do_another_thing(cache)  # Uses cached events
    
    # After appending new events
    self.eventlog.append(...)
    cache.invalidate()  # Clear cache
    events = cache.get_events()  # Fresh read
```

### Option B: Use Existing Snapshot Cache

**Change**:
```python
# Before
events = self.eventlog.read_all()
identity = build_identity(events)
self_model = build_self_model(events)

# After
snapshot = self._get_snapshot()  # Cached until new event
events = snapshot.events
identity = snapshot.identity
self_model = snapshot.self_model
```

**Files to modify**:
- `pmm/runtime/loop.py` (multiple functions)
- `pmm/commitments/tracker.py` (projection-dependent functions)

---

## Testing Strategy

### 1. Before Making Changes

```bash
# Run baseline performance test
python3 scripts/profile_performance.py > baseline_perf.txt

# Run baseline analysis
python3 scripts/analyze_read_all_hotspots.py > baseline_hotspots.txt

# Run full test suite
pytest -q
```

### 2. After Each Fix

```bash
# Run performance test
python3 scripts/profile_performance.py > after_fix_N.txt

# Compare read_all() counts
python3 scripts/analyze_read_all_hotspots.py > after_fix_N_hotspots.txt

# Run tests to ensure no regressions
pytest -q

# Compare results
diff baseline_hotspots.txt after_fix_N_hotspots.txt
```

### 3. Success Criteria

- [ ] `read_all()` calls reduced from 134 to <30 (>77% reduction)
- [ ] All tests passing (707 passed, 4 skipped)
- [ ] No behavior changes (deterministic replay preserved)
- [ ] Autonomy tick overhead <50ms (measure with profiler)

---

## Implementation Order

1. **Start with tick()** - Highest impact (17 calls → 1 call)
2. **Then handle_identity_adopt()** - Second highest (10 calls → 1 call)
3. **Then reflection functions** - Third highest (10 calls → 0 calls)
4. **Then tracker functions** - Fourth highest (6 calls → 1 call)
5. **Finally, implement caching** - Catch remaining calls

**Total expected reduction**: 134 calls → ~20 calls (85% reduction)

---

## Common Pitfalls

### Pitfall 1: Stale Events After Append

**Problem**:
```python
events = self.eventlog.read_all()
# ... use events ...
self.eventlog.append(...)  # New event added
# ... use events again ...  # Still using old events!
```

**Solution**:
```python
events = self.eventlog.read_all()
# ... use events ...
self.eventlog.append(...)  # New event added
events = self.eventlog.read_all()  # Re-read to get new event
# ... use fresh events ...
```

### Pitfall 2: Modifying Function Signatures

**Problem**: Changing function signatures breaks callers.

**Solution**: Use optional parameters with defaults:
```python
def my_function(self, events=None):
    if events is None:
        events = self.eventlog.read_all()
    # ... use events ...
```

This maintains backward compatibility while allowing optimization.

### Pitfall 3: Forgetting to Pass Events

**Problem**: Extracting events at the top but forgetting to pass to helper functions.

**Solution**: Use a checklist:
1. Extract `events = self.eventlog.read_all()` at the top
2. Search for all `self.eventlog.read_all()` in the function
3. Replace each with `events`
4. For helper function calls, add `events` parameter

---

## Monitoring After Fix

Add performance logging to track improvements:

```python
from pmm.runtime.profiler import get_global_profiler

def tick(self):
    profiler = get_global_profiler()
    
    with profiler.measure("tick_total"):
        with profiler.measure("tick_read_events"):
            events = self.eventlog.read_all()
        
        with profiler.measure("tick_process"):
            # ... process events ...
    
    # Periodically log stats
    if tick_no % 100 == 0:
        print(profiler.get_report())
```

---

## Expected Results

### Before Optimization
- `read_all()` calls per tick: **27+**
- Tick overhead: **135ms** (with 1,000 events)
- Tick overhead: **1,350ms** (with 10,000 events)

### After Phase 1
- `read_all()` calls per tick: **3-5**
- Tick overhead: **20-30ms** (with 1,000 events)
- Tick overhead: **200-300ms** (with 10,000 events)

### After Phase 2
- `read_all()` calls per tick: **1**
- Tick overhead: **5-10ms** (with 1,000 events)
- Tick overhead: **50-100ms** (with 10,000 events)

**Total improvement**: 5-10× faster

---

## Need Help?

1. **Review full analysis**: See `docs/PERFORMANCE-BOTTLENECKS-2025-10-04.md`
2. **Run profiler**: `python3 scripts/profile_performance.py`
3. **Check hotspots**: `python3 scripts/analyze_read_all_hotspots.py`
4. **Ask questions**: Document any issues encountered

---

## Rollback Plan

If something breaks:

1. **Revert changes**: `git revert <commit>`
2. **Run tests**: `pytest -q`
3. **Check specific failures**: `pytest -xvs tests/test_<failing_test>.py`
4. **Review diff**: `git diff HEAD~1`

All changes should be backward-compatible (using optional parameters), so rollback should be safe.
