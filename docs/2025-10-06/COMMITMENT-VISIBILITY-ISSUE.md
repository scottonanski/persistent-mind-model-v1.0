# Commitment Visibility Issue - Root Cause Analysis

## The Problem

When asked "How many commitments do you have?", the LLM responds with incorrect information:
- First says "0 commitments"
- Then says "2 commitments" 
- Then says "3 commitments"
- But can't provide details about them

## Root Cause

**Commitments are intentionally excluded from the chat context** to save tokens.

**File**: `pmm/runtime/loop/pipeline.py:84`
```python
include_commitments=False,  # ← Commitments not in context
```

This is a **deliberate design choice**, not a bug. The system expects the LLM to:
1. Recognize when commitment details are needed
2. Query the ledger explicitly
3. Retrieve commitment data on-demand

## Current State

**Ledger has 3 open commitments**:

| ID | CID | Text | Status |
|----|-----|------|--------|
| 1208 | `dfc57b4f...` | "Reassess traits after 5 cycles..." | Open |
| 1250 | `4977cade...` | "Why-mechanics: This adjustment is justified..." | Open |
| 1275 | `d0149ecf...` | "Reflection: focusing on one concrete next-step." | Open |

**LLM Context**: ❌ No commitment data included

## Why the LLM Can't See Them

The context builder is called with:
```python
build_context_from_ledger(
    ...
    include_commitments=False,  # Commitments excluded
    include_reflections=False,  # Reflections excluded
    include_metrics=False,      # Metrics excluded
    ...
)
```

Only the **identity summary** and **MemeGraph** are included by default.

## The Design Intent

The system was designed to:
1. **Keep context compact** - Only include essential identity info
2. **Query on-demand** - LLM should ask for commitments when needed
3. **Use diagnostics flags** - Context builder sets `needs_commitments=True` when appropriate

### Diagnostics Flow

```python
# Context builder detects missing data
diagnostics = {
    "needs_commitments": True,  # Signal that commitments should be queried
    "needs_metrics": True,       # Signal that metrics should be queried
    "needs_reflections": True,   # Signal that reflections should be queried
}

# Runtime loop checks diagnostics
if diagnostics.get("needs_commitments"):
    # Should trigger a follow-up query
    # But this isn't implemented yet
```

## Solutions

### Option 1: Always Include Commitments (Simple)

**File**: `pmm/runtime/loop/pipeline.py:84`

```python
# BEFORE
include_commitments=False,

# AFTER
include_commitments=True,  # Always show commitments in context
```

**Pros**: LLM always has commitment data  
**Cons**: Increases token usage, may hit context limits

---

### Option 2: Dynamic Inclusion Based on Query (Smart)

Detect when the user asks about commitments and include them dynamically:

```python
def build_context_block(..., user_text: str = ""):
    # Detect commitment-related queries
    commitment_keywords = ["commitment", "promise", "goal", "task"]
    needs_commitments = any(kw in user_text.lower() for kw in commitment_keywords)
    
    return build_context_from_ledger(
        ...
        include_commitments=needs_commitments,
        ...
    )
```

**Pros**: Only includes commitments when needed  
**Cons**: Requires query analysis, may miss edge cases

---

### Option 3: Implement Diagnostics Follow-Up (Proper)

The system already has diagnostics flags - just need to use them:

**File**: `pmm/runtime/loop.py` (handle_user_stream)

```python
# After LLM response, check diagnostics
if diagnostics.get("needs_commitments"):
    # Generate follow-up with commitment details
    commitments_text = _build_commitments_followup()
    yield commitments_text
```

**Pros**: Follows the existing architecture  
**Cons**: Requires implementing the follow-up system

---

## Recommended Fix

**Use Option 1 for now** (always include commitments) since:
- Only 3 commitments currently open
- Token cost is minimal (~200 tokens)
- Provides immediate fix
- Can optimize later with Option 2 or 3

### Implementation

```python
# File: pmm/runtime/loop/pipeline.py
# Line 84
include_commitments=True,  # ← Change this
```

Then restart the backend:
```bash
./start-companion.sh
```

---

## Why the 5000-Event Fix Didn't Help

The earlier fix to increase `tail_limit` from 1000 to 5000 **doesn't matter** because:
- Commitments are at IDs 1208, 1250, 1275
- Current max ID is 1496
- All commitments are within the last 1000 events anyway
- The real issue is `include_commitments=False`

The tail limit increase **would** help if:
- Commitments were very old (ID < 500)
- Or if we had 1000+ events since the last commitment

But in this case, the commitments are recent, so the issue is purely the exclusion flag.

---

## Summary

**Root Cause**: Commitments intentionally excluded from context to save tokens  
**Quick Fix**: Set `include_commitments=True` in pipeline.py  
**Proper Fix**: Implement diagnostics-based follow-up system  
**Current Workaround**: None - LLM genuinely can't see commitments

The system is working as designed - it's just that the design assumes a follow-up mechanism that isn't fully implemented yet.
