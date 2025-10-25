# PMM Proposition Document - Action Items

**Date**: October 24, 2025  
**Purpose**: Specific recommendations for maintaining document accuracy

---

## Priority 1: Critical Updates (Do First)

### 1. Add Document Metadata

**Current State**: No version or date information  
**Recommendation**: Add header block

```markdown
---
Document Version: 1.0
Last Verified: October 24, 2025
Codebase Commit: [current commit hash]
Verification Status: APPROVED
Next Review: January 2026
---
```

**Rationale**: Allows readers to assess document freshness

---

### 2. Replace Commit-Specific GitHub Links

**Current State**: Links reference commit `c18bbe0190d948b815fe536decd4cf4599661703`

**Examples**:
- `https://github.com/scottonanski/persistent-mind-model-v1.0/blob/c18bbe0.../pmm/storage/eventlog.py#L280-L288`

**Recommendation**: Use one of these approaches:

**Option A - Relative paths** (Preferred):
```markdown
See `pmm/storage/eventlog.py:280-288` for hash chain implementation
```

**Option B - Branch-based links**:
```markdown
[eventlog.py](https://github.com/scottonanski/persistent-mind-model-v1.0/blob/main/pmm/storage/eventlog.py#L280-L288)
```

**Option C - Version tags**:
```markdown
[eventlog.py v1.0](https://github.com/scottonanski/persistent-mind-model-v1.0/blob/v1.0/pmm/storage/eventlog.py#L280-L288)
```

**Impact**: Prevents broken links as code evolves

---

### 3. Replace Line Numbers with Code References

**Current State**: Many references like "lines 4480-4489"

**Problem**: Code refactoring shifts line numbers

**Recommendation**: Use function/class names instead

**Before**:
```markdown
The code checks if for the last three autonomy ticks [GitHub](https://github.com/.../loop.py#L4552-L4560)
```

**After**:
```markdown
The `_check_novelty_stagnation()` method in `AutonomyLoop` checks if for the last three autonomy ticks...
```

**Alternative**: Include code snippets for critical logic

---

## Priority 2: Clarify Implementation Status

### 4. Add Status Tags to Claims

**Current State**: Mixes implemented and aspirational features

**Examples of Ambiguity**:
- "The loop **likely** reads the last metrics_update event"
- "These templates **can** vary per style"
- "The system **may** wait a few ticks"

**Recommendation**: Add explicit status markers

```markdown
### Reflection Bandit System [IMPLEMENTED ✅]

The multi-armed bandit algorithm varies reflection styles...

### Evolution Kernel [PARTIAL ⚠️]

Infrastructure is complete, but full stage-aware exploitation is not yet active everywhere.

### Autonomous Naming [DISABLED BY DEFAULT 🔒]

Identity proposals are generated but require user confirmation.
```

**Impact**: Eliminates confusion about what's working vs. planned

---

### 5. Document Feature Completeness

**Recommendation**: Add a "Feature Status Matrix" section

```markdown
## Feature Implementation Status

| Feature | Status | Notes |
|---------|--------|-------|
| Event Log Hash Chain | ✅ Complete | Fully implemented and tested |
| OCEAN Trait Tracking | ✅ Complete | All 5 traits active |
| Stage Progression | ✅ Complete | S0→S4 with hysteresis |
| Commitment Extraction | ✅ Complete | Semantic detection working |
| Reflection Bandit | ⚠️ Partial | Context-aware exploitation incomplete |
| Autonomous Naming | 🔒 Disabled | Requires user confirmation |
| Self-Evolution | ⚠️ Partial | Policy application active, kernel experimental |
| Introspection Audits | ✅ Complete | Every 5 ticks by default |
```

---

## Priority 3: Improve Maintainability

### 6. Add Code Snippet Checksums

**Current State**: Code snippets may drift from actual implementation

**Recommendation**: Add verification metadata

```markdown
### Hash Chain Implementation

```python
# Source: pmm/storage/eventlog.py:280-298
# Last verified: 2025-10-24
# Checksum: sha256:abc123...

prev = self._get_last_hash()
cur = self._conn.execute(...)
# ... rest of code
```
```

**Impact**: Enables automated verification of code snippets

---

### 7. Create Automated Verification Script

**Recommendation**: Add `scripts/verify_docs.py`

```python
#!/usr/bin/env python3
"""Verify documentation claims against codebase."""

import ast
import hashlib
from pathlib import Path

def verify_file_exists(path: str) -> bool:
    """Check if referenced file exists."""
    return Path(path).exists()

def verify_function_exists(file: str, function: str) -> bool:
    """Check if function exists in file."""
    # Parse AST and search for function
    pass

def verify_constant_value(file: str, constant: str, expected_value) -> bool:
    """Verify constant has expected value."""
    # Parse and check
    pass

# Run verification suite
# Report discrepancies
```

**Impact**: Catches documentation drift automatically

---

## Priority 4: Enhance Clarity

### 8. Separate Architecture from Implementation

**Current State**: Document mixes "what" with "how"

**Recommendation**: Split into two documents

**Document 1: PMM Architecture (Stable)**
- Conceptual model
- Design principles  
- Event types and their purposes
- Stage progression philosophy

**Document 2: PMM Implementation Guide (Evolving)**
- Specific file locations
- Code examples
- Configuration parameters
- API references

**Impact**: Architecture doc stays stable while implementation doc can evolve

---

### 9. Add Glossary of Terms

**Recommendation**: Define key terms upfront

```markdown
## Glossary

- **IAS (Identity Alignment Score)**: Metric measuring identity stability (0.0-1.0)
- **GAS (Goal Attainment Score)**: Metric measuring commitment completion (0.0-1.0)
- **CID**: Commitment ID, unique identifier for agent goals
- **Tick**: One cycle of the autonomy loop (default: 3 seconds)
- **Ledger**: The append-only event log (SQLite database)
- **Projection**: Derived state computed from ledger events
```

**Impact**: Reduces confusion for new readers

---

### 10. Add Visual Diagrams

**Current State**: Text-heavy descriptions

**Recommendation**: Add architecture diagrams

```markdown
## Event Flow Diagram

```
User Input → Context Builder → LLM Adapter → Event Log
                                                  ↓
                                            Autonomy Loop
                                                  ↓
                                    ┌─────────────┴─────────────┐
                                    ↓                           ↓
                              Metrics Update              Reflections
                                    ↓                           ↓
                              Stage Tracker            Commitments
```
```

**Tools**: Mermaid.js, PlantUML, or ASCII diagrams

---

## Implementation Timeline

### Week 1 (Immediate)
- [ ] Add document metadata header
- [ ] Add feature status tags
- [ ] Create feature status matrix

### Week 2 (High Priority)
- [ ] Replace commit-specific GitHub links
- [ ] Add glossary section
- [ ] Separate architecture from implementation

### Month 1 (Medium Priority)
- [ ] Replace line numbers with function references
- [ ] Add code snippet checksums
- [ ] Create visual diagrams

### Ongoing (Maintenance)
- [ ] Create automated verification script
- [ ] Establish quarterly review process
- [ ] Update implementation guide as code evolves

---

## Success Metrics

**Documentation Quality**:
- ✅ 100% of links are valid and current
- ✅ All code snippets verified within 30 days
- ✅ Feature status clearly marked
- ✅ No ambiguous "likely" or "may" statements

**Maintenance Process**:
- ✅ Automated verification runs on CI/CD
- ✅ Quarterly manual review completed
- ✅ Version stamps updated with each release

---

## Notes for Maintainers

### When Code Changes
1. Run verification script
2. Update affected code snippets
3. Verify line number references
4. Update checksums
5. Bump document version

### When Architecture Changes
1. Update architecture document
2. Mark old features as deprecated
3. Add new features with [NEW] tag
4. Update diagrams

### Before External Use
1. Verify all links work
2. Check feature status is current
3. Ensure no "TODO" or "FIXME" comments
4. Review for clarity and accuracy

---

## Contact

For questions about this verification or to report documentation issues:
- Create issue in repository
- Tag with `documentation` label
- Reference this verification report
