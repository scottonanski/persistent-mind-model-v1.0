# Semantic Migration Summary

## Overview

This document summarizes the comprehensive analysis of CONTRIBUTING.md violations and the path forward to semantic-based systems.

## What Was Analyzed

✅ **Complete codebase scan** for violations of CONTRIBUTING.md lines 66-115 (No Regex or Brittle Keywords)  
✅ **14 violations identified** across runtime logic, validators, parsers, and utilities  
✅ **Priority classification** from CRITICAL to LOW based on impact  
✅ **Detailed semantic replacement designs** for all violation types  
✅ **Implementation roadmap** with 5-phase migration plan

## Key Findings

### Violation Breakdown

| Priority | Count | Files Affected | Impact |
|----------|-------|----------------|--------|
| **CRITICAL** | 3 | `self_evolution.py`, `llm_trait_adjuster.py`, `classifier.py` | Runtime decisions, ledger events |
| **HIGH** | 3 | `validators.py`, `parsers.py`, `manager.py` | Validation, extraction |
| **MEDIUM** | 3 | `insight_scorer.py`, `reflection_guidance.py`, `reflector.py` | Scoring, reflection |
| **LOW** | 5 | `loop.py`, `graph_trigger.py`, `invariants_rt.py`, etc. | Edge cases, helpers |

### Priority #1: TraitDriftManager

**File**: `pmm/personality/self_evolution.py`  
**Lines**: 150-218  
**Violation**: All 10 `_indicates_*` methods use brittle keyword lists

**Example**:
```python
def _indicates_curiosity(self, kind: str, content: str, meta: dict) -> bool:
    curiosity_indicators = ["question", "explore", "learn", "discover", "investigate"]
    content_lower = content.lower()
    return kind == "prompt" and any(
        indicator in content_lower for indicator in curiosity_indicators
    )
```

**Why This Matters**:
- Directly affects personality trait evolution
- Emits `policy_update` events to ledger
- Breaks with different LLM phrasings
- Violates core CONTRIBUTING.md principle

## Recommended Solution

### Semantic Trait Detector (Embedding-Based)

Replace keyword matching with **embedding similarity against curated exemplars**:

```python
class SemanticTraitDetector:
    """Detects trait signals using embedding similarity to exemplars."""
    
    def __init__(self, embedding_adapter):
        self.embedding_adapter = embedding_adapter
        self.exemplars = {
            "curiosity": [
                "I want to explore this topic further",
                "This makes me wonder about the underlying mechanisms",
                "I'm interested in learning more about this",
                # ... 5 more exemplars
            ],
            # ... 9 more trait dimensions
        }
        self.exemplar_embeddings = self._precompute_embeddings()
    
    def detect_trait_signal(self, text: str, trait_dimension: str) -> tuple[bool, float]:
        """Returns (is_match, confidence) using cosine similarity."""
        text_embedding = self.embedding_adapter.embed(text)
        similarities = [
            cosine_similarity(text_embedding, ex_embed)
            for ex_embed in self.exemplar_embeddings[trait_dimension]
        ]
        max_similarity = max(similarities)
        return (max_similarity >= 0.75, max_similarity)
```

### Benefits

✅ **Model-agnostic**: Works across GPT, Claude, Llama, Mistral  
✅ **Robust**: Handles phrasing variations ("I'm curious" vs "I wonder")  
✅ **Auditable**: Log similarity scores for every detection  
✅ **Deterministic**: Same embeddings → same results  
✅ **Maintainable**: Update exemplars in config, not code  
✅ **CONTRIBUTING.md compliant**: Uses semantic similarity, not keywords

## Implementation Roadmap

### Phase 1: TraitDriftManager (Week 1) - CRITICAL
- Design exemplar set for 10 trait dimensions
- Implement `SemanticTraitDetector` with embedding similarity
- Add configuration file for exemplars
- Create A/B test comparing old vs new
- Deploy with feature flag `PMM_USE_SEMANTIC_TRAIT_DETECTION`

**Success Criteria**: ≥95% agreement with human-labeled trait signals

### Phase 2: LLMTraitAdjuster (Week 2) - HIGH
- Replace action word detection with semantic similarity
- Replace confidence scoring with structural analysis
- Add regression tests

### Phase 3: Directive Classifier (Week 3) - HIGH
- Implement embedding-based classification
- Create exemplars for meta-principle/principle/commitment
- Test against existing classifications

### Phase 4: Validators & Parsers (Week 4) - MEDIUM
- Implement structural pattern matching for observables
- Replace commitment extraction with semantic matching
- Update all tests

### Phase 5: Cleanup (Week 5+) - LOW
- Fix insight scorer, reflection guidance, reflector
- Clean up loop handlers
- Final audit and documentation

**Total Estimated Effort**: 3-4 weeks

## Migration Strategy

### Feature Flags
```bash
# Enable semantic trait detection
PMM_USE_SEMANTIC_TRAIT_DETECTION=1

# Enable semantic commitment extraction
PMM_USE_SEMANTIC_COMMITMENTS=1

# Enable semantic directive classification
PMM_USE_SEMANTIC_DIRECTIVES=1
```

### Parallel Execution
During migration, run both old and new systems in parallel:
1. Log detections from both systems
2. Compare results
3. Measure agreement rate
4. Tune thresholds if needed
5. Switch to new system when agreement ≥95%

### Rollback Plan
- Keep old code behind feature flag
- Monitor ledger events for anomalies
- Can instantly revert by disabling flag

## Testing Strategy

### Regression Tests
```python
def test_semantic_vs_keyword_detection():
    """Compare semantic detection to keyword baseline."""
    test_cases = load_labeled_examples()  # 100+ examples
    
    semantic_detector = SemanticTraitDetector(embedding_adapter)
    keyword_detector = TraitDriftManager()  # Old system
    
    agreement_count = 0
    for text, expected_traits in test_cases:
        semantic_result = semantic_detector.detect_trait_signal(text, "curiosity")
        keyword_result = keyword_detector._indicates_curiosity("prompt", text, {})
        
        if semantic_result[0] == keyword_result:
            agreement_count += 1
    
    agreement_rate = agreement_count / len(test_cases)
    assert agreement_rate >= 0.95, f"Agreement rate too low: {agreement_rate}"
```

### Cross-Model Tests
Test with multiple LLM providers:
- GPT-4
- Claude 3.5
- Llama 3
- Mistral

Ensure semantic detection works consistently across all models.

### Performance Tests
- Measure embedding latency
- Optimize with caching
- Ensure <10ms overhead per detection

## Configuration Management

### Exemplar Configuration File
```yaml
# config/semantic_exemplars.yaml

trait_detection:
  version: "1.0.0"
  embedding_model: "text-embedding-3-small"
  
  curiosity:
    threshold: 0.75
    exemplars:
      - "I want to explore this topic further"
      - "This makes me wonder about the underlying mechanisms"
      - "I'm interested in learning more about this"
      - "What if we investigated the root cause"
      - "I'd like to discover how this works"
      - "Let me dig deeper into this question"
      - "I'm curious about the implications"
      - "This raises interesting questions worth exploring"
  
  planning:
    threshold: 0.75
    exemplars:
      - "Let me organize these steps systematically"
      - "I'll prepare a structured approach"
      - "We should schedule this carefully"
      - "I need to plan this out in advance"
      - "Let's create a detailed roadmap"
      - "I'll structure this methodically"
      - "We need to organize our priorities"
  
  # ... 8 more trait dimensions
```

### Benefits of Configuration
- Update exemplars without code changes
- Version control for exemplar sets
- Easy A/B testing of different exemplars
- Audit trail of what exemplars were used

## Audit Trail

Every semantic detection logs:
```python
{
    "kind": "trait_signal_detected",
    "meta": {
        "trait_dimension": "curiosity",
        "is_match": true,
        "confidence": 0.87,
        "matched_exemplar": "I want to explore this topic further",
        "embedding_spec": {
            "model": "text-embedding-3-small",
            "version": "1.0.0"
        },
        "threshold": 0.75,
        "method": "cosine_similarity"
    }
}
```

This provides full auditability and reproducibility.

## Open Questions

1. **Embedding Model**: Use OpenAI (fast, proprietary) or local model (slower, private)?
   - **Recommendation**: Start with OpenAI, add local option later
   
2. **Threshold Tuning**: How to set similarity thresholds?
   - **Recommendation**: Start with 0.75, tune based on A/B test results
   
3. **Backward Compatibility**: Maintain keyword fallback?
   - **Recommendation**: Yes, for 1 release cycle, then remove
   
4. **Exemplar Curation**: Who maintains exemplar sets?
   - **Recommendation**: Version control in `config/`, reviewed in PRs

## Success Metrics

### Technical Metrics
- ✅ Agreement rate with human labels ≥95%
- ✅ Cross-model consistency ≥90%
- ✅ Latency overhead <10ms per detection
- ✅ Zero regex usage in runtime code
- ✅ Zero brittle keyword lists in runtime code

### Business Metrics
- ✅ Trait evolution works across all LLM providers
- ✅ No regression in existing functionality
- ✅ Improved auditability (similarity scores logged)
- ✅ Easier maintenance (exemplars in config, not code)

## Next Steps

1. **Review this analysis** with team
2. **Approve Phase 1 scope** (TraitDriftManager)
3. **Create exemplar set** for 10 trait dimensions
4. **Implement SemanticTraitDetector** with tests
5. **Deploy with feature flag** for A/B testing
6. **Measure results** and tune thresholds
7. **Proceed to Phase 2** if successful

## Documentation

Three documents created:

1. **`CONTRIBUTING-VIOLATIONS-ANALYSIS.md`** - Comprehensive violation catalog
2. **`docs/semantic-replacement-designs.md`** - Detailed implementation designs
3. **`SEMANTIC-MIGRATION-SUMMARY.md`** (this file) - Executive summary

All documents follow CONTRIBUTING.md principles and provide actionable guidance.

---

## Conclusion

The codebase has **14 violations** of CONTRIBUTING.md's "No Brittle Keywords" rule, with **TraitDriftManager being the highest priority fix**.

**Recommended approach**: Implement embedding-based semantic detection using curated exemplars, starting with TraitDriftManager (Phase 1), then expanding to other violations.

**Estimated timeline**: 3-4 weeks for full remediation.

**Key principle**: Replace keyword matching with semantic similarity, as specified in CONTRIBUTING.md lines 82-111.

This migration will make PMM more robust, model-agnostic, and maintainable while improving auditability and determinism.
