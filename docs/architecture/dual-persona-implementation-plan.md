# Dual-Persona Conscience Implementation Plan

**Date:** 2025-10-02  
**Status:** Planning  
**Goal:** Implement Reflector/Executor separation to eliminate meta-statement false positives

## Problem Summary

The current single-pass approach has the LLM generate reflections that sometimes contain meta-statements like "I will query the ledger" or "The system will reply", which get misclassified as commitments because:

1. **Models can't distinguish self-generated text from external input** - they just process tokens
2. **Reflections mix analysis with commitment-like phrases** - using "I will" for both description and intent
3. **The extractor tries to be both speaker and interpreter** - fighting semantic fuzziness

## Architectural Insight

**Current Flow:**
```
LLM generates reflection → Extractor guesses intent → Tracker logs
                          ↑
                    (semantic ambiguity)
```

**Dual-Persona Flow:**
```
Phase 1 (Reflector): LLM generates analysis-only text
                     ↓
                     Logged as reflection event (source=reflector)
                     ↓
Phase 2 (Executor):  Treats reflector text as "external input"
                     ↓
                     Extracts clean, imperative actions
                     ↓
                     Logged as commitment events (source=executor)
```

## Implementation Strategy

### Phase 1: Minimal Changes (Recommended First Step)

**Goal:** Add source tagging and prompt constraints without major refactoring

#### 1.1 Update `emit_reflection()` in `loop.py`

**Location:** Lines 3757-4082

**Changes:**
- Add prompt instruction to ban commitment language in reflection prompts
- Tag reflection events with `meta["source"] = "reflector"`
- Add `meta["persona"] = "reflector"` for clarity

**Modified prompt templates** (lines 3822-3855):
```python
templates = {
    0: (
        "succinct",
        "Reflect on your current IAS/GAS metrics, open commitments, and "
        "trait deltas. **Describe observations only - do NOT use commitment "
        "phrases like 'I will' or 'plan to'.** Focus on analysis and insights. "
        "Propose one concrete system-level action (e.g., adjust novelty threshold, "
        "open/close a commitment). Avoid generic advice unrelated to PMM internals.",
    ),
    # ... similar updates for other templates
}
```

**Meta payload update** (line 3985):
```python
meta_payload = {
    "source": "reflector",  # Changed from "emit_reflection"
    "persona": "reflector",  # New field
    "telemetry": {...},
    # ... rest unchanged
}
```

#### 1.2 Add Executor Phase After Reflection

**Location:** After reflection emission in `emit_reflection()` or in `maybe_reflect()`

**New function:** `extract_executor_commitments()`

```python
def extract_executor_commitments(
    eventlog: EventLog,
    reflection_id: int,
    reflection_text: str,
    llm_generate: callable | None = None,
) -> list[str]:
    """Phase 2: Executor persona extracts commitments from reflector output.
    
    Treats reflection text as external input to leverage model's strength
    in parsing user-like text for intent.
    """
    # Build executor prompt
    executor_prompt = (
        "Review the following analysis and extract ONLY clear, actionable commitments. "
        "Generate short, imperative statements using 'I will' or 'Set' for actions. "
        "If no clear actions are implied, respond with 'No actions'. "
        f"\n\nAnalysis:\n{reflection_text}"
    )
    
    # Call LLM as executor
    if llm_generate:
        try:
            action_text = llm_generate(executor_prompt)
        except Exception:
            action_text = ""
    else:
        action_text = ""
    
    if not action_text or "no actions" in action_text.lower():
        return []
    
    # Extract commitments using existing extractor
    from pmm.commitments.extractor import extract_commitments
    
    commitments = extract_commitments(action_text.splitlines())
    action_candidates = []
    
    for text, intent, score in commitments:
        if intent == "open" and _validate_commitment_structure(text):
            action_candidates.append(text)
    
    return action_candidates

def _validate_commitment_structure(text: str) -> bool:
    """Structural validators for commitments."""
    return (
        len(text) < 400 and
        not any(c in text for c in ["≥", "≤", "**", "##"]) and
        "http" not in text.lower()
    )
```

**Integration point** (in `emit_reflection()` after line 4082 or in `maybe_reflect()` after line 4191):

```python
# After reflection is emitted
if rid is not None:
    # Phase 2: Executor extracts commitments
    try:
        action_candidates = extract_executor_commitments(
            eventlog, 
            int(rid), 
            sanitized_text,
            llm_generate=llm_generate
        )
        
        # Log executor commitments
        tracker = CommitmentTracker(eventlog)
        for action_text in action_candidates:
            tracker.add_commitment(
                text=action_text,
                source="executor",
                extra_meta={
                    "reflection_id": int(rid),
                    "persona": "executor",
                }
            )
    except Exception as e:
        logger.debug(f"Executor phase failed: {e}", exc_info=True)
```

#### 1.3 Update `_extract_commitments_from_text()` in `loop.py`

**Location:** Lines 1162-1237

**Changes:**
- Skip commitment extraction from reflection events
- Only extract from user input and executor output

**Modified logic** (line 1170):
```python
def _extract_commitments_from_text(
    self, text: str, *, source_event_id: int, speaker: str
) -> None:
    """Route semantic commitment intents from free text into the tracker."""
    
    if not text or source_event_id <= 0:
        return
    
    # NEW: Skip extraction from reflector persona
    try:
        source_event = next(
            (e for e in self.eventlog.read_all() 
             if e.get("id") == source_event_id),
            None
        )
        if source_event:
            meta = source_event.get("meta", {})
            if meta.get("persona") == "reflector" or meta.get("source") == "reflector":
                # Reflections are handled by executor phase
                return
    except Exception:
        pass
    
    text_lower = text.lower()
    
    # ... rest of function unchanged

### Phase 2: Persona-Specific Orientation (Chat vs. Conscience)

**Goal:** Keep the conscience persona fully grounded in PMM mechanics while letting the user-facing bot speak naturally.

#### 2.1 Preserve Conscience Orientation
- Leave `orientation_text()` untouched. The conscience (reflections, planning, audits) will continue to read the full ledger-focused prompt.
- No code changes required here beyond ensuring internal calls still use this function.

#### 2.2 Introduce Bot Orientation
- Add a new helper `orientation_text_bot()` in `pmm/runtime/pmm_prompts.py`.
- Key content:
  * Affirm the bot is a persistent, self-evolving identity guided by the ledger.
  * Encourage natural conversation; surface IAS/GAS or commitment mechanics only when the user asks or when they materially help the answer.
  * Remind the bot to defer to the conscience persona when unsure (“consult your internal director”).
- Keep the template concise (< _MAX_ORIENTATION_TOKS) and avoid compliance tone.

Example outline:
```
You are a persistent mind with an identity that grows through ledger memories.
Speak naturally; use ledger evidence when facts matter.
Consult your internal conscience (reflections and commitments) if you need exact details.
Surface IAS/GAS or stage metrics only when requested or essential.
```

#### 2.3 Wire Orientation Into `build_system_msg`
- Update `build_system_msg("chat")` to use `orientation_text_bot()` plus the existing `voice_constraints("chat")` tail.
- Reflections, planning, and other internal kinds should keep calling `orientation_text()`.
- Consider adding a `chat_verbose` variant that still references the conscience for power users.

#### 2.4 Context Builder Guardrails
- Review `build_context_from_ledger()` to ensure the user-facing context mirrors the lighter tone: keep Identity/User, but move raw IAS/GAS tables and commitment lists behind commands such as `--@metrics`.
- Ensure the conscience still has access to the full ledger slice when running reflections.

#### 2.5 Verification
- Regression tests: `pytest tests/test_naming.py`, reflection/commitment suites, and any snapshot tests to confirm hashes or hashes update if needed.
- Manual run: conduct a chat session to ensure greetings and follow-up answers no longer parrot IAS tables by default.
- Monitor that reflections/planning still cite IAS/GAS correctly (to confirm the conscience prompt remains intact).
```

#### 1.4 Update `extractor.py` (Optional Enhancement)

**Location:** Lines 57-70

**Add one more analysis exemplar:**
```python
ANALYSIS_EXEMPLARS: list[str] = [
    # ... existing exemplars
    "The model processes events based on ledger state",
    "When we start a new session the system will query",
]
```

### Phase 2: Testing and Validation

#### 2.1 Update Tests

**File:** `tests/test_commitment_reflection_filter.py`

**Add new tests:**
```python
def test_reflector_persona_no_commitments():
    """Reflector-tagged events should not extract commitments."""
    from pmm.storage.eventlog import EventLog
    from pmm.commitments.tracker import CommitmentTracker
    
    log = EventLog(":memory:")
    
    # Simulate reflector event
    rid = log.append(
        kind="reflection",
        content="I will query the ledger to check state",
        meta={"source": "reflector", "persona": "reflector"}
    )
    
    # Verify no commitments extracted
    tracker = CommitmentTracker(log)
    # ... assertions

def test_executor_persona_extracts_commitments():
    """Executor should extract clean imperatives."""
    # ... test executor phase
```

#### 2.2 Integration Test

**Run fresh DB cycle:**
```bash
pytest tests/test_runtime_commitments.py -v
pytest tests/test_identity.py::test_commitment_close_exact_match_only -v
```

### Phase 3: Monitoring and Iteration

1. **Log executor extractions** for first 20 cycles
2. **Monitor hallucination warnings** (should drop to zero)
3. **Track false positives** in commitment ledger
4. **Adjust exemplars** if new patterns emerge

## Benefits

- ✅ **Eliminates meta-statement problem** (they stay in reflector-only text)
- ✅ **Leverages model strengths** (external intent inference)
- ✅ **Maintains PMM principles** (determinism, autonomy, auditability)
- ✅ **Minimal code changes** (focused on `loop.py`, tests)
- ✅ **Backward compatible** (existing ledgers unaffected)

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Executor generates no actions | Fallback to current behavior; log warning |
| LLM call overhead (2x calls) | Cache reflection text; make executor call optional |
| Breaking existing tests | Update test expectations; add new persona-aware tests |
| Ledger migration needed | No migration - just tag new events going forward |

## Rollout Plan

1. **Week 1:** Implement Phase 1.1-1.3 (source tagging, executor phase)
2. **Week 1:** Update tests (Phase 2.1)
3. **Week 2:** Run integration tests, monitor fresh DB cycles
4. **Week 2:** Adjust exemplars based on monitoring data
5. **Week 3:** Document changes, update CONTRIBUTING.md

## Decision Points

**Before proceeding, confirm:**
- [ ] Should executor phase be mandatory or optional?
- [ ] Should we add executor LLM call or just use extractor on reflection text?
- [ ] Should we migrate existing reflections or only tag new ones?
- [ ] Should we add logging/metrics for executor phase performance?

## Next Steps

1. Review this plan
2. Decide on Phase 1 vs. full implementation
3. Create feature branch: `feature/dual-persona-conscience`
4. Implement changes incrementally
5. Run tests after each change
6. Document learnings

---

**Questions or concerns?** Discuss before implementation.
