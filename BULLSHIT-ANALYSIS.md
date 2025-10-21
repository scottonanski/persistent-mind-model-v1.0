# Codebase Bullshit Analysis

## Executive Summary

The codebase claims to implement a "context-aware bandit" for reflection style selection, but **it's completely fake**. The system logs context metadata but never uses it for decision-making. It's a global bandit pretending to be contextual.

---

## Critical Issues

### 1. **The Context-Aware Bandit Doesn't Exist** 🔴

**Location**: `pmm/runtime/reflection_bandit.py`

**The Lie**: The plan document (`CONTEXT-AWARE-BANDIT-PLAN.md`) claims the system should learn "succinct works in S0, narrative works in S1" - stage-specific arm selection.

**The Reality**:
- `choose_arm()` (line 84-97): Uses **global** epsilon-greedy with no context
- `_arm_rewards()` (line 56-69): Aggregates rewards **globally** across all contexts
- `_best_arm_by_mean()` (line 72-81): Selects best arm using **global** mean

```python
def choose_arm(events: list[dict]) -> tuple[str, int]:
    """Deterministic epsilon-greedy arm selection."""
    tick = _current_tick(events)
    # exploration
    if _rng.random() < _EPSILON:
        arm = ARMS[_rng.randrange(len(ARMS))]
        return (arm, tick)
    # exploitation
    rewards = _arm_rewards(events)  # ← GLOBAL REWARDS
    arm = _best_arm_by_mean(rewards)  # ← GLOBAL BEST
    return (arm, tick)
```

**What's Missing**:
- No stage filtering in reward aggregation
- No context-specific mean computation
- No stage-aware arm selection
- No commitment-count awareness

### 2. **Context Metadata is Logged But Never Used** 🔴

**Location**: `pmm/runtime/loop/reflection.py` lines 662-671

The code **logs** stage context in `bandit_arm_chosen` events:

```python
_io.append_bandit_arm_chosen(
    eventlog,
    arm=_arm_norm,
    tick=int(tick_no_bandit),
    extra={
        "stage": current_stage,  # ← LOGGED BUT NEVER READ
        "source": arm_source,
    },
)
```

But `reflection_bandit.py` **never reads** the `stage` field from these events. It's pure theater.

### 3. **Reward Computation Ignores Context** 🔴

**Location**: `pmm/runtime/reflection_bandit.py` lines 226-263

```python
def compute_reward(events: list[dict], *, horizon: int = 3) -> tuple[float, str | None, int | None]:
    """Return (reward, arm, chosen_tick)..."""
    # Finds last chosen arm
    chosen = None
    for ev in reversed(events):
        if ev.get("kind") == "bandit_arm_chosen":
            chosen = ev
            break
    # ... computes reward using IAS delta and commitment close ratio
    # BUT: Never filters by stage, never considers context
```

The reward is computed globally - it doesn't matter if "succinct" worked well in S0 but poorly in S3. Everything gets mixed together.

### 4. **The Guidance Bias System is Broken** 🟡

**Location**: `pmm/runtime/reflection_guidance.py`

```python
def build_reflection_guidance(events: list[dict], top_k: int = GUIDANCE_MAX) -> dict[str, Any]:
    """Deterministic guidance for reflection, based on active directives."""
    active = build_directives_active_set(events)[: max(0, int(top_k))]
    items = [{"content": r["content"], "score": r["score"]} for r in active]
    # ...
```

**Problems**:
- `build_directives_active_set()` returns items with `content` and `score`
- But `apply_guidance_bias()` expects items with `type` and `score`
- The mapping `ARM_FROM_GUIDANCE_TYPE` requires a `type` field that doesn't exist
- Result: Guidance bias **never actually applies** because the type field is always missing

```python
# In reflection_bandit.py line 125
for it in guidance_items or []:
    arm = ARM_FROM_GUIDANCE_TYPE.get(str(it.get("type") or ""))  # ← "type" doesn't exist!
    if not arm:
        continue  # ← Always continues, never applies bias
```

### 5. **Stage-Based Arm Selection is Hardcoded, Not Learned** 🟡

**Location**: `pmm/runtime/stage_tracker.py` (inferred from tests)

The tests show there's a `policy_arm_for_stage()` function that returns:
- S0 → succinct
- S1 → question_form  
- S2 → analytical
- S3 → narrative
- S4 → checklist

This is **hardcoded policy**, not learned behavior. The bandit doesn't learn these associations - they're just baked in.

### 6. **Massive Code Duplication and Complexity** 🟡

**Location**: Multiple files

- `emit_reflection()` exists in both `loop/reflection.py` (678 lines) and `reflection_bandit.py` (line 316)
- The reflection module is 678 lines of spaghetti with 10+ levels of nesting
- `AutonomyLoop.handle_identity_adopt()` is 437 lines (lines 2246-2683) - a single method!
- Excessive try/except blocks that swallow errors silently

### 7. **Tests Don't Test What They Claim** 🟡

**Location**: `tests/test_stage_policy_arm_wiring.py`

```python
def test_reward_aggregation_normalizes_legacy_question_label(tmp_path):
    """Verify historical rewards with 'question' label are counted as 'question_form'."""
    # ... creates some rewards
    rewards = _arm_rewards(events)
    # Then manually implements normalization logic instead of testing actual code
    acc = {"question_form": []}
    for ev in events:
        # ... manual normalization
        if arm == "question":
            arm = "question_form"  # ← Test does the work, not the code!
```

The test **implements** the normalization instead of verifying the actual code does it.

### 8. **Performance "Optimizations" That Don't Help** 🟡

**Location**: Throughout `loop/reflection.py`

```python
# Line 59
if events is None:
    try:
        events = eventlog.read_tail(limit=1000)  # 5-10x faster than read_all()
    except (AttributeError, TypeError):
        events = eventlog.read_all()  # Fallback
```

Comments claim "5-10x faster" but:
- The tail is still 1000 events (huge)
- Immediately followed by `build_self_model()` which processes all events anyway
- The "optimization" is cargo-culted everywhere without measurement

---

## What Actually Needs to Happen

### For Context-Aware Bandit:

1. **Modify `_arm_rewards()` to accept context filter**:
```python
def _arm_rewards(events: list[dict], stage: str | None = None) -> dict[str, list[float]]:
    scores: dict[str, list[float]] = {a: [] for a in ARMS}
    for ev in events:
        if ev.get("kind") != "bandit_reward":
            continue
        m = ev.get("meta") or {}
        
        # Filter by stage if provided
        if stage is not None:
            ev_stage = m.get("stage")
            if ev_stage != stage:
                continue
        
        arm = str(m.get("arm") or "")
        # ... rest of logic
```

2. **Make `choose_arm()` context-aware**:
```python
def choose_arm(events: list[dict], stage: str | None = None) -> tuple[str, int]:
    tick = _current_tick(events)
    if _rng.random() < _EPSILON:
        arm = ARMS[_rng.randrange(len(ARMS))]
        return (arm, tick)
    
    # Use stage-filtered rewards
    rewards = _arm_rewards(events, stage=stage)
    arm = _best_arm_by_mean(rewards)
    return (arm, tick)
```

3. **Store stage in reward events**:
```python
def maybe_log_reward(eventlog, *, horizon: int = 3) -> int | None:
    # ... existing logic to find unmatched arm
    
    # Get stage at reward time
    events = eventlog.read_all()
    try:
        current_stage, _ = StageTracker.infer_stage(events)
    except Exception:
        current_stage = None
    
    return _io.append_bandit_reward(
        eventlog,
        component="reflection",
        arm=arm_final,
        reward=reward,
        extra={"stage": current_stage},  # ← Add stage context
    )
```

### For Guidance Bias:

Fix the type mismatch:
```python
def build_reflection_guidance(events: list[dict], top_k: int = GUIDANCE_MAX) -> dict[str, Any]:
    active = build_directives_active_set(events)[: max(0, int(top_k))]
    
    # Map content to type for guidance bias
    items = []
    for r in active:
        content = r["content"].lower()
        # Infer type from content keywords
        if "checklist" in content or "list" in content:
            type_hint = "checklist"
        elif "question" in content or "ask" in content:
            type_hint = "question"
        elif "analyze" in content or "analytical" in content:
            type_hint = "analytical"
        elif "story" in content or "narrative" in content:
            type_hint = "narrative"
        else:
            type_hint = "succinct"
        
        items.append({
            "content": r["content"],
            "score": r["score"],
            "type": type_hint  # ← Add the missing field
        })
    
    # ... rest
```

### For Code Quality:

1. **Delete duplicate `emit_reflection()` in `reflection_bandit.py`** (lines 316-338)
2. **Extract `handle_identity_adopt()` into smaller functions** (< 50 lines each)
3. **Remove silent exception swallowing** - log errors or fail fast
4. **Delete fake performance comments** - measure or remove claims

---

## Severity Assessment

| Issue | Severity | Impact | Effort to Fix |
|-------|----------|--------|---------------|
| No context-aware learning | 🔴 Critical | Core feature doesn't work | Medium (2-3 days) |
| Context metadata unused | 🔴 Critical | Wasted computation | Low (1 day) |
| Guidance bias broken | 🟡 High | Feature silently fails | Low (1 day) |
| Hardcoded stage mapping | 🟡 High | Not actually learning | Medium (2 days) |
| Code duplication | 🟡 Medium | Maintenance burden | Medium (2 days) |
| Misleading tests | 🟡 Medium | False confidence | Low (1 day) |
| Fake optimizations | 🟢 Low | Misleading comments | Low (1 hour) |

---

## Recommendations

### Immediate (This Week):
1. Fix guidance bias type mismatch
2. Remove duplicate `emit_reflection()` 
3. Add stage filtering to reward aggregation
4. Update tests to verify actual code behavior

### Short-term (Next Sprint):
1. Implement true context-aware arm selection
2. Store stage in reward events
3. Refactor `handle_identity_adopt()` into smaller functions
4. Add integration test for context-aware learning

### Long-term (Next Quarter):
1. Replace hardcoded stage→arm mapping with learned policy
2. Add commitment-count as context dimension
3. Implement Thompson Sampling for better exploration
4. Add visualization for per-context arm performance

---

## The Bottom Line

The codebase has **good bones** - the event log architecture is solid, the stage tracking works, and the infrastructure for context-aware learning exists. But the actual learning algorithm is **fake**. It's a global bandit with context metadata sprinkled on top for show.

The fix isn't hard - it's mostly plumbing. But it needs to happen before claiming "context-aware" anything.
