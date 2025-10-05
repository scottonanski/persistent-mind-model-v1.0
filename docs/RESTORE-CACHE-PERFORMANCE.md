# Restore Cache Performance - Quick Fix Guide

**Problem**: Refactor bypassed existing 10-80× performance caches  
**Solution**: Use cached APIs instead of direct calls  
**Time**: 1-2 hours  
**Impact**: Restore 10-80× speedup

---

## Quick Reference: Cache API Patterns

### ❌ WRONG (Bypasses Cache)

```python
# Pattern 1: Direct projection (NO CACHE)
events = self.eventlog.read_all()
self_model = build_self_model(events)  # ❌ No eventlog = no cache!

# Pattern 2: Direct metrics (NO CACHE)
events = self.eventlog.read_all()
ias, gas = compute_ias_gas(events)  # ❌ No cache!

# Pattern 3: Multiple reads (NO CACHE)
events1 = self.eventlog.read_all()  # ❌ Read 1
events2 = self.eventlog.read_all()  # ❌ Read 2
events3 = self.eventlog.read_all()  # ❌ Read 3
```

### ✅ CORRECT (Uses Cache)

```python
# Pattern 1: Cached projection (5-50× faster)
self_model = build_self_model(None, eventlog=self.eventlog)  # ✅ Cache!
# Or use snapshot:
snapshot = self._get_snapshot()  # ✅ Cached!
self_model = snapshot.self_model

# Pattern 2: Cached metrics (2-5× faster)
from pmm.runtime.metrics import get_or_compute_ias_gas
ias, gas = get_or_compute_ias_gas(self.eventlog)  # ✅ Cache!

# Pattern 3: Request cache (eliminates redundant reads)
from pmm.runtime.request_cache import RequestCache
cache = RequestCache(self.eventlog)
events = cache.get_events()  # ✅ Read once, cache rest
```

---

## Fix Checklist

### Step 1: Fix Projection Cache (5-50× speedup)

**Search for**:
```bash
grep -n "build_self_model(events" pmm/runtime/loop.py pmm/commitments/tracker.py
```

**Replace pattern**:
```python
# Before
events = self.eventlog.read_all()
model = build_self_model(events)

# After (Option A: Pass eventlog)
model = build_self_model(None, eventlog=self.eventlog)

# After (Option B: Use snapshot cache)
snapshot = self._get_snapshot()
model = snapshot.self_model
```

**Files to fix**:
- [ ] `pmm/runtime/loop.py` (~10 instances)
- [ ] `pmm/commitments/tracker.py` (~5 instances)
- [ ] `pmm/runtime/loop/reflection.py` (~3 instances)
- [ ] `pmm/runtime/loop/assessment.py` (~2 instances)

### Step 2: Fix Metrics Cache (2-5× speedup)

**Search for**:
```bash
grep -n "compute_ias_gas(events" pmm/runtime/loop.py pmm/commitments/tracker.py
```

**Replace pattern**:
```python
# Before
from pmm.runtime.metrics import compute_ias_gas
events = self.eventlog.read_all()
ias, gas = compute_ias_gas(events)

# After
from pmm.runtime.metrics import get_or_compute_ias_gas
ias, gas = get_or_compute_ias_gas(self.eventlog)
```

**Files to fix**:
- [ ] `pmm/runtime/loop.py` (~8 instances)
- [ ] `pmm/commitments/tracker.py` (~2 instances)
- [ ] `pmm/runtime/loop/reflection.py` (~1 instance)

### Step 3: Integrate Request Cache (eliminates 90% of reads)

**Target functions**:
- `AutonomyLoop.tick()` (17 read_all() calls → 1)
- `Runtime.handle_user()` (5 read_all() calls → 1)
- `handle_identity_adopt()` (10 read_all() calls → 1)

**Pattern**:
```python
def tick(self):
    # Add at start of function
    from pmm.runtime.request_cache import RequestCache
    cache = RequestCache(self.eventlog)
    
    # Replace all self.eventlog.read_all() with:
    events = cache.get_events()
    
    # After appending new events:
    self.eventlog.append(...)
    events = cache.get_events(refresh=True)  # Force refresh
```

**Files to fix**:
- [ ] `pmm/runtime/loop.py::AutonomyLoop.tick()`
- [ ] `pmm/runtime/loop.py::Runtime.handle_user()`
- [ ] `pmm/runtime/loop.py::AutonomyLoop.handle_identity_adopt()`

### Step 4: Use Snapshot Cache Consistently

**Pattern**:
```python
# Before (rebuilds everything)
events = self.eventlog.read_all()
identity = build_identity(events)
self_model = build_self_model(events)
ias, gas = compute_ias_gas(events)
stage, _ = StageTracker.infer_stage(events)

# After (uses cached snapshot)
snapshot = self._get_snapshot()  # Cached until new event!
identity = snapshot.identity
self_model = snapshot.self_model
ias = snapshot.ias
gas = snapshot.gas
stage = snapshot.stage
```

**Files to fix**:
- [ ] `pmm/runtime/loop.py` (multiple functions)
- [ ] `pmm/runtime/loop/reflection.py` (multiple functions)

---

## Testing After Each Fix

```bash
# 1. Run tests
pytest -q

# 2. Check read_all() count reduction
python3 scripts/analyze_read_all_hotspots.py

# 3. Verify cache is being used
python3 -c "
from pmm.config import USE_PROJECTION_CACHE, USE_METRICS_CACHE
print(f'Projection cache: {USE_PROJECTION_CACHE}')
print(f'Metrics cache: {USE_METRICS_CACHE}')
"
```

---

## Common Mistakes to Avoid

### Mistake 1: Forgetting eventlog parameter

```python
# ❌ WRONG - No cache
build_self_model(events)

# ✅ CORRECT - Uses cache
build_self_model(None, eventlog=self.eventlog)
```

### Mistake 2: Using old metrics API

```python
# ❌ WRONG - No cache
from pmm.runtime.metrics import compute_ias_gas
ias, gas = compute_ias_gas(events)

# ✅ CORRECT - Uses cache
from pmm.runtime.metrics import get_or_compute_ias_gas
ias, gas = get_or_compute_ias_gas(self.eventlog)
```

### Mistake 3: Not refreshing cache after append

```python
# ❌ WRONG - Stale cache
cache = RequestCache(self.eventlog)
events = cache.get_events()
self.eventlog.append(...)
events = cache.get_events()  # Still old events!

# ✅ CORRECT - Refresh after append
cache = RequestCache(self.eventlog)
events = cache.get_events()
self.eventlog.append(...)
events = cache.get_events(refresh=True)  # Fresh events
```

---

## Expected Results

### Before Fix

```
read_all() calls: 134 total
- tick(): 17 calls
- handle_identity_adopt(): 10 calls
- emit_reflection(): 5 calls
- maybe_reflect(): 5 calls

Performance (10K events):
- Projection: 100-200ms
- Metrics: 200-400ms
- User turn: 800-1600ms
```

### After Fix

```
read_all() calls: ~10 total (92% reduction)
- tick(): 1 call
- handle_identity_adopt(): 1 call
- emit_reflection(): 0 calls (uses passed events)
- maybe_reflect(): 0 calls (uses passed events)

Performance (10K events):
- Projection: 5-10ms (10-20× faster)
- Metrics: 10-20ms (10-20× faster)
- User turn: 50-100ms (16× faster)
```

---

## Verification Commands

```bash
# Count read_all() calls before fix
grep -r "\.read_all()" pmm/runtime/loop.py pmm/commitments/tracker.py | wc -l

# Count cached API usage after fix
grep -r "eventlog=self.eventlog" pmm/runtime/loop.py | wc -l
grep -r "get_or_compute_ias_gas" pmm/runtime/loop.py | wc -l
grep -r "RequestCache" pmm/runtime/loop.py | wc -l

# Verify caches are enabled
python3 -c "from pmm.config import *; print(f'Projection: {USE_PROJECTION_CACHE}, Metrics: {USE_METRICS_CACHE}, Embedding: {USE_EMBEDDING_CACHE}')"
```

---

## Rollback Plan

If something breaks:

```bash
# Revert changes
git diff HEAD > cache_fix.patch
git checkout HEAD -- pmm/runtime/loop.py pmm/commitments/tracker.py

# Run tests
pytest -q

# If tests pass, reapply selectively
git apply --check cache_fix.patch
```

---

## Success Criteria

- [ ] All tests passing (707 passed, 4 skipped)
- [ ] read_all() calls reduced by >90%
- [ ] Projection cache hit rate >80%
- [ ] Metrics cache hit rate >80%
- [ ] Performance restored to pre-refactor levels
- [ ] No behavior changes (deterministic replay preserved)

---

## Quick Start

```bash
# 1. Start with highest impact fix
# Edit pmm/runtime/loop.py::AutonomyLoop.tick()
# Add RequestCache at start, replace read_all() calls

# 2. Test immediately
pytest -q tests/test_autonomy_loop.py

# 3. Continue with other functions
# Fix handle_identity_adopt(), handle_user(), etc.

# 4. Verify improvement
python3 scripts/analyze_read_all_hotspots.py
```

---

**Estimated time**: 1-2 hours  
**Expected improvement**: 10-80× speedup restored  
**Risk**: Very low (using existing, tested APIs)

**Start now!** 🚀
