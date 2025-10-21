# Context-Aware Bandit Implementation Tracking

**Status**: Phase 1 (Immediate Fixes) Complete ✅  
**Next**: Phase 2 (Context-Aware Selection) - Ready to Start

---

## Phase 1: Immediate Fixes ✅ COMPLETE

### 1. ✅ Fix Guidance Bias Type Mismatch
**File**: `pmm/runtime/reflection_guidance.py`  
**Status**: FIXED  
**Changes**:
- Added `type` field inference from content keywords
- Maps content to arm types: checklist, question, analytical, narrative, succinct
- Now compatible with `apply_guidance_bias()` expectations

**Commit**: Guidance items now include `{"content", "score", "type"}` instead of just `{"content", "score"}`

### 2. ✅ Normalize Bandit Labels at Source
**File**: `pmm/runtime/reflection_bandit.py`  
**Status**: FIXED  
**Changes**:
- `_arm_rewards()` now normalizes legacy "question" → "question_form" labels
- Ensures historical rewards aggregate correctly
- Removes dependency on downstream normalization

**Lines**: 80-82

### 3. ✅ Store Stage in Bandit Reward Events
**File**: `pmm/runtime/reflection_bandit.py`  
**Status**: FIXED  
**Changes**:
- `maybe_log_reward()` now extracts stage from `bandit_arm_chosen` events
- Falls back to `StageTracker.infer_stage()` if not captured
- Stores stage in reward event metadata: `extra={"stage": stage_chosen}`

**Lines**: 301-352

### 4. ✅ Remove Duplicate `emit_reflection()`
**File**: `pmm/runtime/reflection_bandit.py`  
**Status**: FIXED  
**Changes**:
- Removed unused duplicate function (lines 316-338)
- Left comment pointing to canonical implementation in `pmm.runtime.loop.reflection`

### 5. ✅ Fix Runtime Recreation Bug
**File**: `pmm/api/companion.py`  
**Status**: FIXED  
**Changes**:
- Cache by `(db_path, model)` tuple instead of EventLog instance identity
- Prevents unnecessary autonomy loop restarts on every request
- Added debug logging for cache hits

**Lines**: 68-108

### 6. ✅ Fix "use the name" Index Bug
**File**: `pmm/runtime/loop.py`  
**Status**: FIXED  
**Changes**:
- Changed from `text_lower.find()` + `commit_text[idx:]` (wrong basis)
- To `commit_text_lower.find()` + `commit_text[idx:]` (correct basis)
- Prevents silent failures in identity name extraction

**Lines**: 990-994

### 7. ✅ Replace NGramFilter with SubstringFilter
**File**: `pmm/runtime/loop.py`  
**Status**: FIXED  
**Changes**:
- Import changed from `NGramFilter` to `SubstringFilter`
- Instantiation updated (line 473)
- Eliminates deprecation warnings in test output

---

## Phase 2: Context-Aware Selection ✅ COMPLETE

### Issue #1: Context-Aware Arm Selection
**Priority**: HIGH  
**Effort**: 2-3 days  
**Status**: ✅ COMPLETE

**What's Done**:
- ✅ Stage stored in reward events
- ✅ `_arm_rewards()` accepts `stage` parameter
- ✅ `choose_arm()` accepts `stage` parameter
- ✅ Label normalization in place
- ✅ Stage wired through `maybe_reflect()` call chain
- ✅ Context-aware selection active in `loop/reflection.py`
- ✅ Integration tests verify stage-filtered learning

**Implementation Complete**:
```python
# pmm/runtime/loop/reflection.py:589-637
# Priority 1: Use guidance-biased selection if guidance available
if isinstance(arm_means, dict) and isinstance(guidance_items, list):
    arm, _delta_b = _choose_arm_biased(arm_means, guidance_items)
    arm_source = "bandit_biased"

# Priority 2: Use context-aware epsilon-greedy selection
if arm is None:
    arm, _tick = _choose_arm_contextual(events_now_bt, stage=current_stage)
    arm_source = "bandit_contextual" if current_stage else "bandit"

# Priority 3: Fall back to last reflection's template
if arm is None:
    # ... fallback logic
```

**Files Modified**:
- ✅ `pmm/runtime/loop/reflection.py` (lines 589-637)
- ✅ `pmm/runtime/loop/io.py` (added `extra` param to `append_bandit_reward`)
- ✅ `tests/test_contextual_bandit_learning.py` (new integration tests)

**Test Coverage** (5 new tests):
- ✅ `test_stage_filtered_reward_aggregation` - Verifies stage filtering works
- ✅ `test_context_aware_arm_selection_exploitation` - Verifies stage-specific preferences
- ✅ `test_legacy_label_normalization_in_context` - Verifies "question" → "question_form"
- ✅ `test_rewards_without_stage_metadata_aggregate_globally` - Backward compatibility
- ✅ `test_context_aware_selection_with_no_stage_history` - Cold start handling

---

### Issue #2: Update Tests for Code Behavior
**Priority**: MEDIUM  
**Effort**: 1 day  
**Status**: Tests currently implement logic they should verify

**Problem**:
`tests/test_stage_policy_arm_wiring.py:116-157` manually normalizes labels instead of testing actual code:

```python
# Current (wrong):
for ev in events:
    arm = str(m.get("arm") or "")
    if arm == "question":
        arm = "question_form"  # Test does the work!
    acc["question_form"].append(r)

# Should be:
rewards = _arm_rewards(events)  # Code does the work
assert len(rewards["question_form"]) == 3
```

**Files to Fix**:
- `tests/test_stage_policy_arm_wiring.py` (lines 116-157)
- Add new test: `test_arm_rewards_normalizes_legacy_labels()`

---

### Issue #3: Integration Test for Context Learning
**Priority**: MEDIUM  
**Effort**: 1 day  
**Status**: New test needed

**Goal**: Verify the system actually learns stage-specific preferences

**Test Outline**:
```python
def test_bandit_learns_stage_specific_preferences():
    """
    Verify bandit learns different arms work better in different stages.
    
    Setup:
    - Create S0 context, choose succinct, high reward
    - Create S1 context, choose question_form, high reward
    - Create S0 context, choose narrative, low reward
    
    Verify:
    - In S0, exploitation chooses succinct (not narrative)
    - In S1, exploitation chooses question_form
    - Global mean doesn't override stage-specific learning
    """
```

**File**: `tests/test_contextual_bandit_learning.py` (new)

---

## Phase 3: Long-Term Improvements 📋 BACKLOG

### Replace Hardcoded Stage→Arm Mapping
**Priority**: LOW  
**Effort**: 2 days  
**Status**: Not blocking

**Current**: `pmm/runtime/stage_tracker.py:41` has static mapping:
```python
def policy_arm_for_stage(stage: str) -> str | None:
    return {"S0": "succinct", "S1": "question_form", ...}.get(stage)
```

**Goal**: Remove hardcoded policy, let bandit learn optimal arms per stage

**Approach**:
1. Keep hardcoded mapping as fallback for cold start
2. After N rewards per stage, switch to learned policy
3. Add `learned_policy_active` flag to metadata

---

### Add Commitment-Count as Context Dimension
**Priority**: LOW  
**Effort**: 2 days  
**Status**: Future enhancement

**Goal**: Learn "succinct works when 0-2 commitments open, analytical works when 5+ open"

**Changes**:
- Extend context tuple: `(stage, commitment_bucket)` where bucket = "low" | "medium" | "high"
- Filter rewards by both dimensions
- Update reward storage to include commitment count

---

### Thompson Sampling for Better Exploration
**Priority**: LOW  
**Effort**: 3 days  
**Status**: Research needed

**Current**: Epsilon-greedy (10% random exploration)  
**Better**: Thompson Sampling (Bayesian exploration based on uncertainty)

**Benefits**:
- More efficient exploration (explores uncertain arms, not random)
- Natural handling of context switching
- Better cold-start performance

---

### Visualization Dashboard
**Priority**: LOW  
**Effort**: 3 days  
**Status**: Nice-to-have

**Goal**: UI showing per-stage arm performance over time

**Features**:
- Heatmap: stages × arms → mean reward
- Line chart: arm performance evolution per stage
- Exploration vs exploitation ratio
- Recent arm choices with context

**Tech**: Add endpoint to companion API, integrate into Next.js UI

---

## Testing Strategy

### Unit Tests (Existing)
- ✅ `tests/test_reflection_bandit.py` - Basic bandit mechanics
- ✅ `tests/test_stage_policy_arm_wiring.py` - Label normalization
- 🔄 Need update: Remove manual normalization logic

### Integration Tests (Needed)
- ⏳ `tests/test_contextual_bandit_learning.py` - Stage-aware learning
- ⏳ `tests/test_guidance_bias_application.py` - Type field usage

### System Tests (Future)
- ⏳ End-to-end: Multiple stages, verify different arms chosen
- ⏳ Regression: Ensure legacy rewards still aggregate correctly

---

## Documentation Updates Needed

### README.md
- ✅ Hash verification claim (already noted in BULLSHIT-ANALYSIS.md)
- ✅ IAS/GAS constants (already noted)
- ⏳ Add section on context-aware bandit behavior

### CONTRIBUTING.md
- ⏳ Document bandit architecture
- ⏳ Explain stage context filtering
- ⏳ Testing guidelines for bandit changes

### Architecture Docs
- ⏳ Create `docs/architecture/context-aware-bandit.md`
- ⏳ Diagram: Event flow from choice → reward → next choice
- ⏳ Explain cold start vs learned policy

---

## Rollout Plan

### Week 1 (Current)
- ✅ Phase 1 complete (all immediate fixes)
- ⏳ PR review and merge

### Week 2
- ⏳ Issue #1: Wire stage context through selection
- ⏳ Issue #2: Fix test implementations
- ⏳ Verify no regressions in existing tests

### Week 3
- ⏳ Issue #3: Integration test for learning
- ⏳ Documentation updates
- ⏳ Performance testing (ensure stage filtering doesn't slow down)

### Month 2+
- ⏳ Phase 3 enhancements (as needed)
- ⏳ Monitor production behavior
- ⏳ Tune epsilon, horizon, and other hyperparameters

---

## Success Metrics

### Immediate (Phase 1)
- ✅ All tests pass with no deprecation warnings
- ✅ Guidance bias applies (verify in logs)
- ✅ Runtime doesn't restart unnecessarily
- ✅ Legacy rewards aggregate correctly

### Short-term (Phase 2)
- ⏳ Stage-filtered selection active in production
- ⏳ Different arms chosen in different stages (verify in telemetry)
- ⏳ Reward aggregation shows stage-specific patterns

### Long-term (Phase 3)
- ⏳ Learned policy outperforms hardcoded mapping
- ⏳ Exploration rate decreases over time (confidence increases)
- ⏳ Reflection quality scores improve per stage

---

## Notes

- All Phase 1 fixes are backward compatible
- No breaking changes to event schema
- Stage filtering is opt-in (works without stage if not provided)
- Legacy rewards without stage metadata still aggregate globally

## References

- **Original Plan**: `CONTEXT-AWARE-BANDIT-PLAN.md` (if exists)
- **Gap Analysis**: `BULLSHIT-ANALYSIS.md`
- **Code Locations**:
  - Bandit core: `pmm/runtime/reflection_bandit.py`
  - Reflection logic: `pmm/runtime/loop/reflection.py`
  - Guidance builder: `pmm/runtime/reflection_guidance.py`
  - Tests: `tests/test_reflection_bandit.py`, `tests/test_stage_policy_arm_wiring.py`
