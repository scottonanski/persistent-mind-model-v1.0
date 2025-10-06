# Regex and Brittle Keyword Violations Audit

## Project Rule

From `CONTRIBUTING.md`:

> **No Regular Expressions or Brittle Keywords in Runtime Logic**
> 
> Regex patterns must not be used in PMM runtime code (ledger parsing, metrics, event validation, etc.)
> 
> **Reasons:**
> - Regex introduces fragile edge cases
> - Regex undermines determinism and auditability  
> - Regex is hard to audit and conflicts with PMM's kernel invariants (truth-first, reproducibility)

**Correct Approach**: Semantic matching via embedding similarity against exemplar sets.

---

## Audit Results

### ✅ No Direct Regex Imports

**Good news**: No `import re` found in runtime code.

---

### ⚠️ Brittle Keyword Matching Violations

Found **multiple violations** of keyword-based logic in runtime:

---

## 1. **Trait Adjustment Action Detection** (HIGH SEVERITY)

**File**: `pmm/runtime/llm_trait_adjuster.py`

**Lines 224-234**:
```python
if action.lower() in ["decrease", "decreasing", "reduce", "lower"]:
    delta = -abs(delta)
elif action.lower() in ["increase", "increasing", "raise", "boost"]:
    delta = abs(delta)
```

**Lines 253-261**:
```python
if "because" in suggestion_text.lower() or "since" in suggestion_text.lower():
    confidence += 0.1  # Has reasoning

if any(word in suggestion_text.lower() for word in ["maybe", "might", "could"]):
    confidence -= 0.1  # Hesitant language
```

**Issue**: Hard-coded keyword lists for detecting trait adjustment intent.

**Fix**: Use semantic classifier with exemplars:
```python
# GOOD: Semantic intent detection
from pmm.commitments.extractor import classify_action_intent

intent = classify_action_intent(action_text)
if intent.direction == "increase":
    delta = abs(delta)
elif intent.direction == "decrease":
    delta = -abs(delta)
```

---

## 2. **Commitment Rebinding Name Matching** (MEDIUM SEVERITY)

**File**: `pmm/runtime/loop.py`

**Lines 2322, 2481, 2510**:
```python
if str(old_name).lower() in txt_pre.lower():
    # Rebind commitment
```

**Issue**: Substring matching for identity name changes in commitments.

**Fix**: Use semantic similarity:
```python
# GOOD: Semantic name matching
from pmm.embeddings import compute_similarity

if compute_similarity(old_name, commitment_text) > 0.85:
    # Rebind commitment
```

---

## 3. **Identity Source Validation** (LOW SEVERITY)

**File**: `pmm/runtime/invariants_rt.py`

**Line 173**:
```python
if str(src).strip().lower() in {"user", "assistant"}:
    has_proposal = True
```

**Issue**: Keyword matching for source validation.

**Fix**: Use enum or constant:
```python
# GOOD: Enum-based validation
from pmm.config import IdentitySource

if src in {IdentitySource.USER, IdentitySource.ASSISTANT}:
    has_proposal = True
```

---

## 4. **Name Banlist Check** (LOW SEVERITY)

**File**: `pmm/runtime/loop/identity.py`

**Line 80**:
```python
if token.lower() in NAME_BANLIST:
    return None
```

**Issue**: Keyword-based filtering.

**Fix**: This is acceptable if `NAME_BANLIST` is a small, stable set of reserved words. But should be documented as an exception.

---

## 5. **Capitalized Word Extraction** (MEDIUM SEVERITY)

**File**: `pmm/runtime/loop/handlers.py`

**Lines 188, 513**:
```python
if len(t) > 1 and t[0].isupper() and t.lower() not in common:
    cands.append(t)
```

**Issue**: Heuristic-based name extraction using capitalization.

**Fix**: Use NER (Named Entity Recognition) or semantic name classifier:
```python
# GOOD: Semantic name detection
from pmm.identity.name_classifier import extract_names

names = extract_names(text, context="identity_proposal")
```

---

## 6. **Environment Variable Parsing** (LOW SEVERITY)

**File**: `pmm/runtime/llm_trait_adjuster.py`

**Line 526**:
```python
if os.getenv("PMM_LLM_TRAIT_ADJUSTMENTS", "1").lower() not in ("1", "true", "yes"):
    return []
```

**Issue**: Keyword-based boolean parsing.

**Fix**: Use proper boolean parsing:
```python
# GOOD: Proper boolean parsing
from pmm.config import parse_bool_env

if not parse_bool_env("PMM_LLM_TRAIT_ADJUSTMENTS", default=True):
    return []
```

---

## Summary

| Violation | File | Severity | Fix Priority |
|-----------|------|----------|--------------|
| Trait action keywords | `llm_trait_adjuster.py` | 🔴 High | Immediate |
| Commitment name matching | `loop.py` | 🟡 Medium | Soon |
| Capitalized word extraction | `loop/handlers.py` | 🟡 Medium | Soon |
| Identity source validation | `invariants_rt.py` | 🟢 Low | Later |
| Name banlist | `loop/identity.py` | 🟢 Low | Document exception |
| Env var parsing | `llm_trait_adjuster.py` | 🟢 Low | Later |

---

## Recommended Fixes

### Priority 1: Trait Adjuster (Immediate)

Replace keyword lists with semantic classifier:

```python
# pmm/runtime/llm_trait_adjuster.py

from pmm.commitments.extractor import classify_trait_action

def _parse_trait_delta(suggestion_text: str) -> tuple[str | None, float | None]:
    """Parse trait name and delta from suggestion using semantic classification."""
    result = classify_trait_action(suggestion_text)
    
    if not result.is_valid:
        return None, None
    
    delta = result.magnitude  # Semantic extraction of magnitude
    if result.direction == "decrease":
        delta = -abs(delta)
    elif result.direction == "increase":
        delta = abs(delta)
    
    return result.trait_name, delta
```

### Priority 2: Commitment Rebinding (Soon)

Replace substring matching with semantic similarity:

```python
# pmm/runtime/loop.py

from pmm.embeddings import compute_similarity

def should_rebind_commitment(old_name: str, commitment_text: str) -> bool:
    """Determine if commitment should be rebound based on semantic similarity."""
    similarity = compute_similarity(old_name, commitment_text)
    return similarity > 0.85  # Threshold for name reference
```

### Priority 3: Name Extraction (Soon)

Replace heuristics with NER or semantic classifier:

```python
# pmm/runtime/loop/handlers.py

from pmm.identity.name_classifier import extract_candidate_names

def extract_names_from_text(text: str) -> list[str]:
    """Extract candidate names using semantic classification."""
    return extract_candidate_names(
        text,
        context="identity_proposal",
        min_confidence=0.7
    )
```

---

## Testing Plan

After fixes, verify:

1. **Trait adjustments** still work with varied phrasing:
   - "boost openness"
   - "make me more open"
   - "increase O by 0.05"
   
2. **Commitment rebinding** still triggers on name changes:
   - "I'm now called Alice" → rebinds commitments mentioning old name
   
3. **Name extraction** still works:
   - "Call me Bob" → extracts "Bob"
   - "My name is Charlie" → extracts "Charlie"

---

## Conclusion

The runtime has **6 categories of keyword-based logic** that violate the no-regex/no-keywords principle. Most are low-severity, but the trait adjuster is high-priority because it directly affects personality evolution.

**Next steps**:
1. Implement semantic classifiers for trait actions
2. Replace substring matching with embedding similarity
3. Document exceptions (e.g., NAME_BANLIST) if they're acceptable

The good news: No actual regex usage found, so the violations are limited to keyword matching which is easier to fix.
