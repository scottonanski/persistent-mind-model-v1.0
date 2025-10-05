# Refactor Plan: Semantic Action Extraction (No Brittle Markers)

**Date**: 2025-10-02  
**Status**: PROPOSED  
**Goal**: Replace brittle marker filtering with structural separation and semantic validation

---

## Current Problem

We're in a **whack-a-mole pattern** adding markers:
```python
reflection_markers = [
    "gas ≥", "ias ≥", "indicates", "leverages", "aligns with", ...
]
```

This violates CONTRIBUTING.md principles:
- ❌ No brittle keyword matching
- ❌ Marker lists keep growing
- ❌ Breaks with new LLM phrasing

**Root cause**: Semantic extractor can't distinguish:
- "I will adjust the threshold" (action)
- "This action leverages the threshold to improve alignment" (analysis)

Both match commitment patterns semantically.

---

## Solution: Structural Separation + Semantic Validation

### Phase 1: Explicit Structural Separation (Immediate)

**Change reflection prompt to enforce structure:**

```python
# Current (mixed analysis + action):
"Reflect on your current IAS/GAS metrics... Propose one concrete system-level action..."

# New (separated):
"""
Reflect on your current state and analyze the situation.

Then, on a new line starting with "ACTION:", state ONE concrete next step as a commitment.

Format:
Analysis: [your reflection here]
ACTION: [imperative statement, max 50 words]

Example:
Analysis: IAS is low at 0.18, indicating weak alignment...
ACTION: Adjust novelty threshold to 0.45
"""
```

**Benefits**:
- LLM explicitly separates analysis from action
- Parser looks for "ACTION:" prefix
- No semantic ambiguity

**Implementation**:
1. Update reflection templates in `emit_reflection()` (loop.py:3855-3889)
2. Parse for "ACTION:" line in action extraction (loop.py:2972-2995)
3. Extract only the text after "ACTION:"

---

### Phase 2: Structural Validators (Medium-term)

**Add validators to `tracker.add_commitment()`:**

```python
def add_commitment(self, text: str, source: str | None = None, ...):
    # Structural validation (no markers needed)
    if not _is_valid_commitment_structure(text):
        return ""  # Reject silently
    
    # Continue with normal flow...
```

**Validators**:

```python
def _is_valid_commitment_structure(text: str) -> bool:
    """Validate commitment structure without brittle markers."""
    
    # 1. Length constraint (deterministic)
    if len(text) > MAX_COMMITMENT_CHARS:
        return False
    
    # 2. Token count (prevents verbose analysis)
    tokens = text.split()
    if len(tokens) > 50:  # ~40-50 words max
        return False
    
    # 3. No comparison operators (structural, not keyword)
    if any(op in text for op in ['≥', '≤', '>=', '<=', '==', '!=']):
        return False
    
    # 4. No markdown formatting (analysis uses this)
    if any(md in text for md in ['**', '##', '- ', '* ']):
        return False
    
    # 5. Imperative/declarative form (semantic check)
    # Use existing semantic extractor to verify it matches "open" intent
    from pmm.commitments.extractor import CommitmentExtractor
    extractor = CommitmentExtractor()
    analysis = extractor.detect_intent(text)
    
    if analysis["intent"] != "open" or analysis["score"] < 0.65:
        return False
    
    return True
```

**Benefits**:
- ✅ No brittle markers
- ✅ Structural rules are deterministic
- ✅ Semantic validation via existing extractor
- ✅ Rejects analysis automatically

---

### Phase 3: Exemplar-based Dual Matching (Long-term)

**Enhance semantic extractor with negative exemplars:**

```python
# In extractor.py
COMMITMENT_EXEMPLARS = {
    "open": [
        "I will complete this task",
        "I plan to work on this",
        "Adjust the threshold to 0.45",  # Imperative
        "Set openness to 0.52",
    ],
}

# NEW: Analysis exemplars (to reject)
ANALYSIS_EXEMPLARS = {
    "reflection": [
        "This action leverages the threshold",
        "The system indicates growth",
        "Aligns with our growth mechanics",
        "Expected IAS is 0.35",
    ],
}

def detect_intent(self, text: str) -> dict:
    # Existing commitment matching
    commit_score = max(cosine_similarity(vec, ex_vec) 
                       for ex_vec in commitment_exemplars)
    
    # NEW: Analysis matching (negative signal)
    analysis_score = max(cosine_similarity(vec, ex_vec) 
                         for ex_vec in analysis_exemplars)
    
    # Commitment if: high commit score AND low analysis score
    if commit_score > 0.62 and analysis_score < 0.50:
        return {"intent": "open", "score": commit_score}
    
    return {"intent": "none", "score": 0.0}
```

**Benefits**:
- ✅ Learns what analysis looks like
- ✅ Rejects analytical phrasing semantically
- ✅ No marker lists needed
- ✅ Adapts to new phrasings

---

## Implementation Roadmap

### Step 1: Structural Separation (1-2 hours)
**Files to modify**:
- `pmm/runtime/loop.py` (reflection templates)
- `pmm/runtime/loop.py` (action extraction parser)

**Changes**:
1. Update reflection prompts to request "ACTION:" format
2. Parse for "ACTION:" prefix in extraction
3. Extract only text after "ACTION:"

**Testing**:
- Update reflection tests to expect "ACTION:" format
- Verify clean action extraction

---

### Step 2: Structural Validators (2-3 hours)
**Files to modify**:
- `pmm/commitments/tracker.py` (add validators)

**Changes**:
1. Create `_is_valid_commitment_structure()` function
2. Call validator in `add_commitment()` before creating event
3. Return empty string if validation fails (silent rejection)

**Testing**:
- Test validator rejects long text
- Test validator rejects markdown
- Test validator rejects comparison operators
- Test validator accepts clean commitments

---

### Step 3: Remove Brittle Markers (30 min)
**Files to modify**:
- `pmm/runtime/loop.py` (remove marker lists)

**Changes**:
1. Delete `reflection_markers` lists (lines 1206-1240, 3096-3104)
2. Remove marker-based filtering
3. Rely on structural validators instead

**Testing**:
- All existing tests should still pass
- Commitments should be cleaner

---

### Step 4: Exemplar-based Dual Matching (3-4 hours, optional)
**Files to modify**:
- `pmm/commitments/extractor.py`

**Changes**:
1. Add `ANALYSIS_EXEMPLARS` dictionary
2. Update `detect_intent()` to compute analysis score
3. Require high commit score AND low analysis score

**Testing**:
- Test extractor rejects analytical phrasing
- Test extractor accepts clean commitments
- Verify no false positives

---

## Expected Outcomes

### Before (Current State)
```python
# Brittle marker filtering
if any(marker in text.lower() for marker in [
    "gas ≥", "ias ≥", "indicates", "leverages", ...  # 30+ markers
]):
    reject()
```

**Problems**:
- Marker list keeps growing
- Breaks with new phrasing
- Hard to maintain

### After (Structural + Semantic)
```python
# Structural validation
if len(text) > 400 or len(tokens) > 50:
    reject()

if any(op in text for op in ['≥', '≤', '**']):
    reject()

# Semantic validation
if commit_score > 0.62 and analysis_score < 0.50:
    accept()
else:
    reject()
```

**Benefits**:
- ✅ No marker lists
- ✅ Deterministic rules
- ✅ Semantic understanding
- ✅ Adapts to new phrasings

---

## Compliance with CONTRIBUTING.md

✅ **No regex** - Using structural rules and semantic similarity  
✅ **No brittle keywords** - Using exemplar-based matching  
✅ **Semantic-based** - Embedding similarity for intent detection  
✅ **Deterministic** - Structural rules are reproducible  
✅ **Auditable** - Clear validation logic, no hidden markers  

---

## Migration Strategy

### Option A: Big Bang (Recommended)
1. Implement Steps 1-3 in one PR
2. Update all tests
3. Deploy with fresh DB

**Pros**: Clean break, no technical debt  
**Cons**: Larger change, more testing needed

### Option B: Incremental
1. Deploy Step 1 (structural separation) first
2. Then Step 2 (validators)
3. Then Step 3 (remove markers)

**Pros**: Smaller changes, easier to test  
**Cons**: Temporary hybrid state, more PRs

---

## Success Metrics

After implementation:
1. **Zero marker lists** in runtime code ✅
2. **Commitments ≤ 50 words** (structural enforcement) ✅
3. **No analytical phrasing** in commitments ✅
4. **All tests passing** ✅
5. **No whack-a-mole** pattern ✅

---

## Next Steps

1. **Review this plan** - Confirm approach aligns with vision
2. **Choose migration strategy** - Big bang vs incremental
3. **Implement Step 1** - Structural separation in reflection prompts
4. **Test with fresh DB** - Verify clean action extraction
5. **Continue with Steps 2-4** - Build out validators and dual matching

---

**Ready to proceed?** This refactor will eliminate brittle markers and align with PMM's semantic-first design principles.
