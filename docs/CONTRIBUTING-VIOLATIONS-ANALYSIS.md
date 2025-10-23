# CONTRIBUTING.md Violations Analysis

## Executive Summary

This document identifies all violations of CONTRIBUTING.md's "No Regex or Brittle Keywords" rule across the PMM codebase, prioritizes them by severity, and proposes semantic-based replacements.

**Key Finding**: The codebase has **14 critical violations** using brittle keyword matching in runtime logic, with `TraitDriftManager` being the highest priority fix.

---

## Priority Classification

### **PRIORITY 1: CRITICAL - Runtime Decision Logic**

These violations directly affect runtime behavior and ledger events.

#### 1. **TraitDriftManager** (`pmm/personality/self_evolution.py`)
**Severity**: CRITICAL  
**Lines**: 150-218 (all semantic detection methods)  
**Violation**: Uses brittle keyword lists for personality trait detection

**Current Implementation**:
```python
def _indicates_curiosity(self, kind: str, content: str, meta: dict) -> bool:
    curiosity_indicators = ["question", "explore", "learn", "discover", "investigate"]
    content_lower = content.lower()
    return kind == "prompt" and any(
        indicator in content_lower for indicator in curiosity_indicators
    )
```

**Problems**:
- Breaks with phrasing changes ("I'm curious" vs "question")
- Different LLMs use different language patterns
- Hard to maintain as keyword lists grow
- Violates CONTRIBUTING.md lines 76-81

**Impact**: Trait evolution is fragile and model-dependent

---

#### 2. **LLMTraitAdjuster** (`pmm/runtime/llm_trait_adjuster.py`)
**Severity**: HIGH  
**Lines**: 117-186, 224-234, 253-260  
**Violation**: Keyword matching for trait suggestion parsing

**Current Implementation**:
```python
# Line 224-227
if action.lower() in ["decrease", "decreasing", "reduce", "lower"]:
    delta = -abs(delta)
elif action.lower() in ["increase", "increasing", "raise", "boost"]:
    delta = abs(delta)

# Line 253-254
if "because" in suggestion_text.lower() or "since" in suggestion_text.lower():
    confidence += 0.1  # Has reasoning
```

**Problems**:
- Brittle action word detection
- Confidence scoring based on keyword presence
- Won't work with different phrasings

---

#### 3. **SemanticDirectiveClassifier** (`pmm/directives/classifier.py`)
**Severity**: HIGH  
**Lines**: 330-522 (all indicator scoring methods)  
**Violation**: Uses keyword lists despite being named "Semantic"

**Current Implementation**:
```python
def _analyze_temporal_scope(self, text: str, words: list[str]) -> str:
    immediate_indicators = {
        "verbs": ["will", "plan", "intend", "aim", "commit"],
        "time_refs": ["today", "tomorrow", "next", "soon", "immediately"],
    }
    # Scores based on keyword presence
```

**Problems**:
- Misnamed - not actually semantic
- Large keyword dictionaries (lines 334-478)
- Fragile classification logic

---

### **PRIORITY 2: HIGH - Validation & Parsing**

#### 4. **Validators** (`pmm/runtime/validators.py`)
**Lines**: 149-164, 224-234, 253-260, 300-304  
**Violation**: Keyword matching for observable detection, gate validation

```python
# Line 152-153
if term in s_lower:
    return True

# Line 156-162
if "within" in s_lower and "turn" in s_lower:
    # Pattern matching logic
```

---

#### 5. **Parsers** (`pmm/utils/parsers.py`)
**Lines**: 260, 409-418, 421-439, 442-467, 470-483  
**Violation**: Keyword matching for commitment extraction

```python
# Line 409-418
if "committed to" in sent_lower:
    first_person = ["i ", "my ", "i'm ", "i've ", "i'll "]
    if any(fp in sent_lower for fp in first_person):
        # Extract commitment
```

**Note**: Some parsers are acceptable (e.g., `extract_event_ids` uses deterministic token parsing, not keywords)

---

#### 6. **Bridge Manager** (`pmm/bridge/manager.py`)
**Lines**: 131-171  
**Violation**: Keyword-based sanitization

```python
_STRIP_PREFIX_PHRASES = [
    "as an ai language model",
    "as a language model",
    # ... 7 more phrases
]
```

**Note**: This may be acceptable as it's sanitization, not decision logic

---

### **PRIORITY 3: MEDIUM - Reflection & Scoring**

#### 7. **Insight Scorer** (`pmm/runtime/insight_scorer.py`)
**Lines**: 59-74  
**Violation**: Keyword-based scoring

```python
if "next" in lower and "step" in lower:
    actionability = 0.7
if "because" in lower or "so that" in lower:
    novelty = min(1.0, novelty + 0.1)
```

---

#### 8. **Reflection Guidance** (`pmm/runtime/reflection_guidance.py`)
**Lines**: 28-33  
**Violation**: Keyword-based type inference

```python
if "checklist" in content_lower or "list" in content_lower:
    type_hint = "checklist"
elif "question" in content_lower or "ask" in content_lower:
    type_hint = "question"
```

---

#### 9. **Reflector** (`pmm/runtime/reflector.py`)
**Lines**: 194-198  
**Violation**: Policy keyword detection

```python
policy_keywords = ["novelty_threshold", "policy:", "lower", "increase", "decrease"]
policy_count = sum(1 for kw in policy_keywords if kw in t_lower)
```

---

### **PRIORITY 4: LOW - Loop Handlers**

#### 10. **Loop** (`pmm/runtime/loop.py`)
**Lines**: 1022-1025, 1138-1141, 1213-1216, 2715-2716, 2744-2745  
**Violation**: Various keyword checks

```python
# Line 1022-1025
if "use the name" in text_lower:
    commit_text_lower = commit_text.lower()
    idx = commit_text_lower.find("use the name")

# Line 1138-1141
if "novelty_threshold" in lowered or "novelty threshold" in lowered:
    # Extract numeric value
```

---

#### 11. **Graph Trigger** (`pmm/runtime/graph_trigger.py`)
**Lines**: 88-90  
**Violation**: Context boost phrase detection

```python
if any(kw in lowered for kw in _CONTEXT_BOOST_PHRASES):
    return True
```

---

#### 12. **Invariants RT** (`pmm/runtime/invariants_rt.py`)
**Lines**: 260  
**Violation**: Name matching in commitment text

```python
if new_name.lower() in commit_text.lower():
    # Check for rebind
```

---

#### 13. **Commitment Tracker** (`pmm/commitments/tracker.py`)
**Lines**: 153-154  
**Violation**: Name matching for rebinding

```python
if (str(old_name).lower() in txt.lower()) or (identity_adopt_event_id is not None):
    # Emit rebind
```

---

#### 14. **Loop Validators** (`pmm/runtime/loop/validators.py`)
**Lines**: 89-90  
**Violation**: Lazy commitment detection

```python
if "commit" not in reply_lower:
    return
```

---

## Semantic-Based Replacement Designs

### **Design 1: Embedding-Based Similarity (Recommended for TraitDriftManager)**

**Architecture**:
```python
class SemanticTraitDetector:
    """Detects trait-relevant patterns using embedding similarity."""
    
    def __init__(self, embedding_model):
        self.embedding_model = embedding_model
        
        # Define exemplars for each trait dimension
        self.exemplars = {
            "curiosity": [
                "I want to explore this topic further",
                "This makes me wonder about...",
                "I'm interested in learning more",
                "What if we investigated...",
                "I'd like to discover..."
            ],
            "routine_preference": [
                "I prefer the usual approach",
                "Let's stick with what works",
                "The standard method is best",
                "I like the familiar way"
            ],
            # ... more exemplars for all 10 trait indicators
        }
        
        # Pre-compute exemplar embeddings
        self.exemplar_embeddings = self._compute_exemplar_embeddings()
    
    def detect_trait_signal(self, text: str, trait_dimension: str) -> tuple[bool, float]:
        """
        Detect if text indicates a trait dimension using semantic similarity.
        
        Returns:
            (is_match, confidence) where confidence is cosine similarity score
        """
        text_embedding = self.embedding_model.embed(text)
        exemplar_embeds = self.exemplar_embeddings[trait_dimension]
        
        # Compute max similarity to any exemplar
        similarities = [
            cosine_similarity(text_embedding, ex_embed)
            for ex_embed in exemplar_embeds
        ]
        
        max_similarity = max(similarities)
        threshold = 0.75  # Configurable threshold
        
        return (max_similarity >= threshold, max_similarity)
```

**Benefits**:
- Works across different phrasings
- Model-agnostic (same exemplars work for GPT, Claude, Llama)
- Auditable (log similarity scores)
- Deterministic (same embeddings → same results)

**Implementation Path**:
1. Use existing `pmm/llm/factory.py` embedding infrastructure
2. Store exemplar embeddings in config file
3. Add `semantic_trait_detector.py` module
4. Replace `TraitDriftManager._indicates_*` methods
5. Add tests comparing old vs new behavior

---

### **Design 2: Structural Pattern Matching (For Validators)**

**Architecture**:
```python
class StructuralValidator:
    """Validates text structure without keyword matching."""
    
    def has_observable_clause(self, text: str) -> bool:
        """Detect observable clauses by structure, not keywords."""
        
        # Parse into semantic units
        units = self._parse_semantic_units(text)
        
        for unit in units:
            # Check for measurable structure:
            # 1. Contains comparison operator (>, <, >=, <=, =)
            # 2. Contains numeric value
            # 3. Contains noun phrase (subject being measured)
            if (unit.has_comparison_operator() and 
                unit.has_numeric_value() and 
                unit.has_noun_phrase()):
                return True
        
        return False
    
    def _parse_semantic_units(self, text: str) -> list[SemanticUnit]:
        """Parse text into semantic units using dependency parsing."""
        # Use spaCy or similar for structural analysis
        # Returns units with grammatical structure, not keywords
```

**Benefits**:
- Detects intent through structure, not words
- More robust to phrasing variations
- Can detect novel observable patterns

---

### **Design 3: Few-Shot LLM Classification (For Directive Classifier)**

**Architecture**:
```python
class FewShotDirectiveClassifier:
    """Classifies directives using few-shot LLM prompting."""
    
    def __init__(self, llm_adapter):
        self.llm = llm_adapter
        self.examples = self._load_classification_examples()
    
    def classify_directive(self, text: str) -> dict:
        """Classify using few-shot prompting."""
        
        prompt = self._build_classification_prompt(text)
        response = self.llm.complete(prompt, max_tokens=50)
        
        # Parse structured response
        classification = self._parse_classification(response)
        
        # Log to ledger for auditability
        self._log_classification(text, classification, response)
        
        return classification
    
    def _build_classification_prompt(self, text: str) -> str:
        """Build few-shot prompt with examples."""
        return f"""
Classify the following directive as meta-principle, principle, or commitment.

Examples:
{self._format_examples()}

Directive: {text}
Classification (meta-principle/principle/commitment):
"""
```

**Benefits**:
- Leverages LLM's semantic understanding
- No keyword lists to maintain
- Can handle novel directive types
- Fully auditable (log prompts + responses)

**Tradeoffs**:
- Requires LLM call (adds latency)
- Non-deterministic (but can use temperature=0 for consistency)
- Needs careful prompt engineering

---

## Implementation Roadmap

### **Phase 1: TraitDriftManager (Week 1)**
**Priority**: CRITICAL  
**Effort**: 3-5 days

1. Design exemplar set for all 10 trait indicators
2. Implement `SemanticTraitDetector` with embedding similarity
3. Add configuration for similarity thresholds
4. Create A/B test comparing old vs new detection
5. Update tests to use semantic detection
6. Deploy with feature flag

**Success Criteria**:
- ≥95% agreement with human-labeled trait signals
- Works across GPT-4, Claude, Llama models
- All tests pass

---

### **Phase 2: LLMTraitAdjuster (Week 2)**
**Priority**: HIGH  
**Effort**: 2-3 days

1. Replace action word detection with semantic similarity
2. Replace confidence scoring with structural analysis
3. Add regression tests
4. Deploy

---

### **Phase 3: Directive Classifier (Week 3)**
**Priority**: HIGH  
**Effort**: 3-4 days

**Option A**: Embedding-based (faster, deterministic)
1. Create exemplar sets for meta-principle/principle/commitment
2. Implement similarity-based classification
3. Test against existing classifications

**Option B**: Few-shot LLM (more flexible, non-deterministic)
1. Curate few-shot examples
2. Implement prompt-based classification
3. Add caching for common directives

---

### **Phase 4: Validators & Parsers (Week 4)**
**Priority**: MEDIUM  
**Effort**: 4-5 days

1. Implement structural pattern matching for observables
2. Replace commitment extraction with semantic matching
3. Update all tests

---

### **Phase 5: Lower Priority Items (Week 5+)**
**Priority**: LOW  
**Effort**: 2-3 days

1. Fix insight scorer, reflection guidance, reflector
2. Clean up loop handlers
3. Final audit

---

## Testing Strategy

### **Regression Testing**
- Create test suite with 100+ examples of each pattern type
- Compare old vs new behavior
- Require ≥95% agreement for deployment

### **Cross-Model Testing**
- Test with GPT-4, Claude, Llama 3, Mistral
- Ensure semantic detection works across all models
- Document any model-specific quirks

### **Performance Testing**
- Measure latency impact of embedding calls
- Optimize with caching where needed
- Ensure <10ms overhead per detection

---

## Open Questions

1. **Embedding Model Selection**: Use OpenAI embeddings (fast, proprietary) or local model (slower, private)?
2. **Threshold Tuning**: How to set similarity thresholds? A/B test? Manual tuning?
3. **Backward Compatibility**: Should we maintain keyword fallback for a transition period?
4. **Audit Trail**: How much to log? Every similarity score? Just decisions?

---

## Conclusion

The codebase has **14 violations** of the "No Brittle Keywords" rule, with `TraitDriftManager` being the most critical. 

**Recommended Approach**:
1. **Phase 1**: Fix TraitDriftManager with embedding-based detection (highest ROI)
2. **Phase 2-3**: Fix LLMTraitAdjuster and DirectiveClassifier
3. **Phase 4-5**: Clean up remaining violations

**Estimated Total Effort**: 3-4 weeks for full remediation

**Key Principle**: Replace keyword matching with semantic similarity using embeddings and exemplar matching, as specified in CONTRIBUTING.md lines 82-111.
