# Commitment Bug Analysis & Fix

## Problem Statement

**Symptom**: Commitments don't persist reliably. The Conscientiousness (C) trait doesn't climb as expected.

**Root Cause Identified**:

1. **Line 120-121 in `pmm/commitments/tracker.py`**:
   ```python
   # Free-text commitment opening is disabled; use explicit structural events
   return []
   ```
   The `process_assistant_reply()` method is **disabled** and returns empty list.

2. **`_extract_commitments_from_text()` in `pmm/runtime/loop.py` (line 935)**:
   - Method exists and implements semantic extraction
   - **BUT**: It's never called from anywhere in the codebase
   - The extraction logic is orphaned

## What Should Happen

1. When assistant generates a response containing commitment intent (e.g., "I will implement X")
2. Semantic extractor detects the commitment using embedding similarity
3. `commitment_open` event is emitted to ledger
4. Commitment tracked in open commitments map
5. When fulfilled, `commitment_close` event emitted
6. Conscientiousness trait increases

## What Actually Happens

1. Assistant generates response with commitment intent
2. **Nothing happens** - extraction is disabled
3. No `commitment_open` events
4. No commitment tracking
5. Conscientiousness stays flat

## The Fix

### Option 1: Re-enable `process_assistant_reply()` (Quick Fix)

**File**: `pmm/commitments/tracker.py`

**Change**:
```python
def process_assistant_reply(
    self, text: str, reply_event_id: int | None = None
) -> list[str]:
    """Detect commitments in assistant replies and open them.

    Returns list of newly opened commitment ids (cids).
    """
    # Expire old commitments (TTL) opportunistically on assistant activity
    try:
        self.expire_old_commitments()
    except Exception:
        pass
    
    # BEFORE (disabled):
    # return []
    
    # AFTER (re-enabled with semantic extraction):
    if not text:
        return []
    
    from pmm.commitments.extractor import extract_commitments
    
    # Extract commitments using semantic similarity
    segments = [s.strip() for s in text.split('.') if s.strip()]
    matches = extract_commitments(segments)
    
    opened_cids = []
    for commit_text, intent, score in matches:
        if intent == "open":
            cid = self.add_commitment(
                commit_text,
                source="assistant",
                extra_meta={"score": score, "reply_event_id": reply_event_id}
            )
            if cid:
                opened_cids.append(cid)
    
    return opened_cids
```

**Pros**:
- Minimal change
- Uses existing semantic extractor
- Preserves TTL expiration logic

**Cons**:
- Duplicates extraction logic (also in `loop.py`)
- Doesn't leverage the more sophisticated `_extract_commitments_from_text()` method

---

### Option 2: Wire Up `_extract_commitments_from_text()` (Better Fix)

**File**: `pmm/runtime/loop.py`

**Find where assistant responses are logged** and add extraction call:

```python
# After assistant response is logged to eventlog
response_event_id = self.eventlog.append(
    kind="response",
    content=assistant_response,
    meta={"source": "assistant"}
)

# ADD THIS: Extract commitments from response
self._extract_commitments_from_text(
    assistant_response,
    source_event_id=response_event_id,
    speaker="assistant"
)
```

**Pros**:
- Uses the existing, well-tested extraction method
- Handles paragraph-aware extraction
- Filters out reflector persona (analysis-only text)
- Emits `commitment_scan` instrumentation events

**Cons**:
- Need to find the right place to call it (response logging location)

---

### Option 3: Hybrid Approach (Recommended)

1. **Re-enable `process_assistant_reply()`** with simple extraction
2. **Keep `_extract_commitments_from_text()`** for reflection-driven commitments
3. **Add call site** in response handling

**Benefits**:
- Catches commitments from both assistant responses AND reflections
- Preserves existing instrumentation
- Minimal risk

---

## Implementation Plan

### Step 1: Re-enable Basic Extraction

Edit `pmm/commitments/tracker.py` line 107-121:

```python
def process_assistant_reply(
    self, text: str, reply_event_id: int | None = None
) -> list[str]:
    """Detect commitments in assistant replies and open them."""
    try:
        self.expire_old_commitments()
    except Exception:
        pass
    
    if not text:
        return []
    
    from pmm.commitments.extractor import extract_commitments
    
    # Simple sentence splitting
    segments = []
    for sent in text.split('.'):
        s = sent.strip()
        if s and len(s) > 10:  # Skip very short fragments
            segments.append(s)
    
    if not segments:
        return []
    
    matches = extract_commitments(segments)
    opened_cids = []
    
    for commit_text, intent, score in matches:
        if intent == "open":
            try:
                cid = self.add_commitment(
                    commit_text,
                    source="assistant",
                    extra_meta={
                        "score": float(score),
                        "reply_event_id": reply_event_id
                    }
                )
                if cid:
                    opened_cids.append(cid)
            except Exception:
                continue
    
    return opened_cids
```

### Step 2: Wire Up Call Site

Find where `tracker.process_assistant_reply()` is called and ensure it's invoked.

**Search for**:
```bash
grep -r "process_assistant_reply" pmm/
```

If not called anywhere, add it after response logging.

### Step 3: Test

```bash
# Run commitment extraction tests
pytest tests/test_commitment_extractor.py -v

# Run integration test
pytest tests/test_commitment_tracker.py -v

# Manual test
python -m pmm.cli.companion --db test_commitments.db
# Type: "I will write a test function"
# Check: python -m pmm.cli.inspect --db test_commitments.db --kind commitment_open
```

### Step 4: Verify Metrics

After fix:
1. Run session with commitments
2. Check `commitment_open` events appear
3. Verify Conscientiousness trait increases
4. Confirm IAS climbs with commitment fulfillment

---

## Expected Impact

### Before Fix
- Commitment open rate: 0%
- Conscientiousness: Flat at ~0.50
- IAS contribution from commitments: 0%

### After Fix
- Commitment open rate: 30-50% (depending on assistant behavior)
- Conscientiousness: Climbs to 0.65-0.75
- IAS contribution from commitments: 15-25%

---

## Regression Risk

**Low Risk** because:
1. Extraction logic already exists and is tested
2. Just re-enabling disabled code
3. Semantic extractor has threshold (0.62) to prevent false positives
4. Idempotency guards prevent duplicate commitments

**Mitigation**:
- Run full test suite before/after
- Monitor `commitment_scan` events for false positives
- Adjust threshold if needed (env var `COMMITMENT_THRESHOLD`)

---

## Alternative: Lower Threshold First

If commitments still don't appear after re-enabling:

```bash
# Try lower threshold temporarily
export COMMITMENT_THRESHOLD=0.50

# Run session
python -m pmm.cli.companion --db test.db

# Check extraction events
python -m pmm.cli.inspect --db test.db --kind commitment_scan
```

The `commitment_scan` events show best detected intent/score even when below threshold.

---

## Next Steps After Fix

1. **Run Session 2 replica** with fix applied
2. **Measure commitment fulfillment rate** (should be >80%)
3. **Verify Conscientiousness climbs** (should reach 0.70+)
4. **Compare IAS trajectory** to original Session 2
5. **Document results** in `REPRODUCIBILITY.md`

---

**Status**: Ready to implement  
**Priority**: HIGH (blocks trait development study)  
**Estimated Time**: 30 minutes to implement + test  
**Risk Level**: LOW
