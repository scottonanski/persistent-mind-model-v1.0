# Next Steps: Commitment Bug Fix

## What We Know (Session 3 Analysis)

### ✅ Working
- Identity stability (Echo remained Echo)
- Stage progression (S0→S4 in ~2300 events)
- Validators (caught hallucinations, issued corrections)
- Philosophical coherence (consistent reasoning across 70+ turns)
- GAS maxed at 1.0 (measuring growth acceleration)

### ❌ Broken
- **Commitment persistence**: Opens fire, but commitments vanish
- **Conscientiousness trait**: Stuck at 0.00 (no fulfillment reinforcement)
- **Lifecycle tracking**: No close/expire events despite opens

### 🔍 Evidence
```
Signals: commit:accepted score=0.88 src=assistant  ← Extraction works
Open commitments: 0→2→3→1→0→1→0                    ← Persistence fails
Conscientiousness: 0.08 → 0.00                     ← Trait decays correctly
```

---

## Implementation Plan

### Phase 1: Diagnose (30 minutes)

#### Step 1: Run Lifecycle Test
```bash
cd /home/scott/Documents/Projects/Business-Development/persistent-mind-model-v1.0
python scripts/test_commitment_lifecycle.py
```

**This will test**:
1. Can we open a commitment manually?
2. Does it appear in the open map?
3. Is the event logged correctly?
4. Can we close it?
5. Does it disappear from open map?

**Expected outcomes**:
- ✅ If this passes → Bug is in extraction/integration
- ❌ If this fails → Bug is in core tracker logic

#### Step 2: Analyze Session 3 Database
```bash
python scripts/analyze_commitment_bug.py .data/echo.db
```

**This will show**:
- How many `commitment_open` events exist
- How many `commitment_close` events exist
- Which CIDs were opened but never closed
- Extraction success rate (scans vs opens)
- Error patterns

**Look for**:
- Zero `commitment_open` events → Extraction completely broken
- Many opens, zero closes → Lifecycle bug
- High-score rejections → Threshold too high

#### Step 3: Check Diagnostic Logs (After Next Session)

With the new logging added, run a fresh session:
```bash
python -m pmm.cli.companion --db test_debug.db
```

Then check:
```bash
python -m pmm.cli.inspect --db test_debug.db --kind commitment_debug
python -m pmm.cli.inspect --db test_debug.db --kind commitment_error
```

**This will reveal**:
- Which commitments successfully opened (with CIDs)
- Which commitments failed (with error messages)
- Exact failure points

---

### Phase 2: Fix Based on Diagnosis (1-2 hours)

#### Scenario A: Extraction Threshold Too High

**Symptom**: Many `commitment_scan` events, few `commitment_open` events

**Fix**: Lower threshold temporarily
```bash
export COMMITMENT_THRESHOLD=0.50
python -m pmm.cli.companion --db test.db
```

**Permanent fix**: Adjust in `pmm/commitments/extractor.py`

#### Scenario B: Idempotency Guard Too Strict

**Symptom**: `commitment_error` events with "duplicate" messages

**Fix**: Check `tracker.py` line ~50-100 for duplicate detection logic
```python
# Look for code like:
if cid in existing_cids:
    raise ValueError("Duplicate commitment")
```

Adjust to allow legitimate duplicates (same text, different context).

#### Scenario C: TTL Expiration Too Aggressive

**Symptom**: Commitments open, then vanish without `commitment_expire` events

**Fix**: Check `expire_old_commitments()` in `tracker.py`
```python
def expire_old_commitments(self):
    # Check TTL logic here
    # May be expiring too quickly
```

Increase default TTL or disable auto-expiration during replies.

#### Scenario D: Projection Cache Invalidation

**Symptom**: Events logged correctly, but `_open_commitments_legacy()` returns empty

**Fix**: Check `pmm/storage/projection_cache.py`
```python
# Look for cache invalidation logic
# May need to force refresh after commitment_open
```

---

### Phase 3: Verify Fix (30 minutes)

#### Test 1: Run Lifecycle Test Again
```bash
python scripts/test_commitment_lifecycle.py
```

Should now pass all tests.

#### Test 2: Run Fresh Session
```bash
python -m pmm.cli.companion --db test_fixed.db
```

Interact for ~50 events, making explicit commitments:
- "I will analyze this problem"
- "I commit to providing a detailed answer"
- "My goal is to help you debug this"

Then check:
```bash
python scripts/analyze_commitment_bug.py .data/test_fixed.db
```

**Success criteria**:
- Multiple `commitment_open` events
- Commitments persist in open map
- Conscientiousness trait starts climbing (C > 0.05)

#### Test 3: Run Session 4 Replica
```bash
python -m pmm.cli.companion --db session4.db
```

Run for ~2000 events with standardized prompts.

**Expected results**:
- S0→S1→S2→S3→S4 (gradual progression, not skip)
- Conscientiousness climbs to 0.65-0.75
- IAS/GAS still reach high values
- Commitment fulfillment rate >80%

---

## Quick Reference Commands

### Run Tests
```bash
# Lifecycle test
python scripts/test_commitment_lifecycle.py

# Analyze existing database
python scripts/analyze_commitment_bug.py .data/echo.db

# Check diagnostic logs
python -m pmm.cli.inspect --db test.db --kind commitment_debug
python -m pmm.cli.inspect --db test.db --kind commitment_error
```

### Run Sessions
```bash
# Test session with debug logging
python -m pmm.cli.companion --db test_debug.db

# Lower threshold temporarily
COMMITMENT_THRESHOLD=0.50 python -m pmm.cli.companion --db test.db

# Full session replica
python -m pmm.cli.companion --db session4.db
```

### Analyze Results
```bash
# View all commitment events
python -m pmm.cli.inspect --db test.db --kind commitment_open
python -m pmm.cli.inspect --db test.db --kind commitment_close

# Full trajectory analysis
python scripts/analyze_trajectory.py test.db
```

---

## Expected Timeline

| Phase | Task | Time | Status |
|-------|------|------|--------|
| 1.1 | Run lifecycle test | 5 min | ⏳ Ready |
| 1.2 | Analyze Session 3 DB | 5 min | ⏳ Ready |
| 1.3 | Run debug session | 20 min | ⏳ Ready |
| 2.1 | Identify root cause | 30 min | ⏳ Pending |
| 2.2 | Implement fix | 30 min | ⏳ Pending |
| 2.3 | Code review | 15 min | ⏳ Pending |
| 3.1 | Test lifecycle | 5 min | ⏳ Pending |
| 3.2 | Test fresh session | 20 min | ⏳ Pending |
| 3.3 | Session 4 replica | 60 min | ⏳ Pending |
| **Total** | | **~3 hours** | |

---

## Success Criteria

### Minimum Viable Fix
- ✅ Lifecycle test passes
- ✅ Commitments persist across events
- ✅ Conscientiousness trait climbs (C > 0.05)

### Full Success
- ✅ All above
- ✅ Stage progression is gradual (S0→S1→S2→S3→S4)
- ✅ Commitment fulfillment rate >80%
- ✅ Session 4 trajectory matches Session 2 baseline

---

## Rollback Plan

If fix breaks something:

1. **Revert diagnostic logging**:
   ```bash
   git checkout pmm/commitments/tracker.py
   ```

2. **Restore original extraction**:
   The extraction re-enable is already committed. If needed:
   ```bash
   git log --oneline pmm/commitments/tracker.py
   git revert <commit-hash>
   ```

3. **Test with dummy provider**:
   ```bash
   PMM_PROVIDER=dummy python -m pmm.cli.companion --db test.db
   ```

---

## What Happens After Fix

### Immediate Impact
- Commitments persist reliably
- Conscientiousness trait develops
- More accurate IAS calculation (commitment component works)

### Research Impact
- Can run ablation study: commitments ON vs OFF
- Can measure causal effect on stage progression
- Can validate "commitment → C trait → IAS" pipeline

### Publication Impact
- Demonstrates reproducible trait development
- Shows goal-directed behavior emergence
- Validates full cognitive architecture

---

## Questions to Answer

1. **Does fixing commitments change stage progression?**
   - Hypothesis: S0→S1→S2→S3→S4 becomes gradual (not skip)
   - Test: Compare Session 4 (fixed) vs Session 2/3 (broken)

2. **What's the natural C trait ceiling?**
   - Hypothesis: C climbs to 0.70-0.80 with healthy commitments
   - Test: Track C over 2000 events with fix applied

3. **Does commitment fulfillment affect IAS?**
   - Hypothesis: IAS climbs faster with working commitments
   - Test: Compare IAS trajectories (fixed vs broken)

4. **Can we skip stages even with working commitments?**
   - Hypothesis: Rapid growth still skips stages
   - Test: Fresh DB with high-quality prompts

---

## Files Changed

### Modified
- `pmm/commitments/tracker.py` (diagnostic logging added)

### Created
- `scripts/test_commitment_lifecycle.py` (lifecycle test)
- `scripts/analyze_commitment_bug.py` (database analysis)
- `NEXT-STEPS.md` (this file)

### To Be Modified (Pending Diagnosis)
- TBD based on test results

---

## Contact Points

If you get stuck:

1. **Lifecycle test fails** → Bug is in core tracker
   - Check `pmm/commitments/tracker.py` lines 40-100
   - Look at `add_commitment()` and `close_commitment()`

2. **Extraction test fails** → Bug is in integration
   - Check `pmm/runtime/loop.py` for `process_assistant_reply()` calls
   - Verify extraction threshold in config

3. **Database analysis shows zero opens** → Extraction completely broken
   - Check `pmm/commitments/extractor.py`
   - Verify semantic similarity logic

4. **Opens exist but vanish** → Projection/cache bug
   - Check `pmm/storage/projection.py`
   - Check `pmm/storage/projection_cache.py`

---

**Status**: Ready to diagnose  
**Next Action**: Run `python scripts/test_commitment_lifecycle.py`  
**Estimated Time to Fix**: 3 hours  
**Risk Level**: LOW (diagnostic logging is non-invasive)
