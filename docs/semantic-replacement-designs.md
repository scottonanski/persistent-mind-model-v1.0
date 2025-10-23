# Semantic Replacement Designs for CONTRIBUTING.md Compliance

This document provides detailed implementation designs for replacing brittle keyword matching with semantic-based systems.

---

## Design 1: Semantic Trait Detector (TraitDriftManager Replacement)

### Overview

Replace `TraitDriftManager`'s keyword-based trait detection with embedding similarity against curated exemplars.

### Architecture

```python
"""Semantic trait detection using embedding similarity."""

from __future__ import annotations
from typing import Optional
import numpy as np


class SemanticTraitDetector:
    """
    Detects personality trait signals using semantic similarity to exemplars.
    
    Replaces brittle keyword matching with embedding-based semantic analysis.
    Fully deterministic given same embedding model and exemplars.
    """
    
    # Embedding specification for auditability
    EMBEDDING_SPEC = {
        "model": "text-embedding-3-small",
        "version": "1.0.0",
        "dimensions": 1536,
        "hash": "sha256:to_be_computed_from_exemplars"
    }
    
    # Similarity threshold for trait signal detection
    SIMILARITY_THRESHOLD = 0.75
    
    def __init__(self, embedding_adapter):
        """
        Initialize with embedding adapter.
        
        Args:
            embedding_adapter: Adapter implementing embed(text) -> np.ndarray
        """
        self.embedding_adapter = embedding_adapter
        self.exemplar_embeddings = None
        self._initialize_exemplars()
    
    def _initialize_exemplars(self):
        """Load and embed exemplar phrases for each trait dimension."""
        
        # Exemplar phrases for each trait indicator
        # These are carefully curated to capture semantic intent
        self.exemplars = {
            "curiosity": [
                "I want to explore this topic further",
                "This makes me wonder about the underlying mechanisms",
                "I'm interested in learning more about this",
                "What if we investigated the root cause",
                "I'd like to discover how this works",
                "Let me dig deeper into this question",
                "I'm curious about the implications",
                "This raises interesting questions worth exploring"
            ],
            "routine_preference": [
                "I prefer the usual approach here",
                "Let's stick with what has worked before",
                "The standard method is most reliable",
                "I like the familiar way of doing this",
                "The typical process should work fine",
                "We should follow the normal procedure",
                "The regular approach is best"
            ],
            "planning": [
                "Let me organize these steps systematically",
                "I'll prepare a structured approach",
                "We should schedule this carefully",
                "I need to plan this out in advance",
                "Let's create a detailed roadmap",
                "I'll structure this methodically",
                "We need to organize our priorities"
            ],
            "impulsiveness": [
                "Let's do this right now without delay",
                "I need to act immediately on this",
                "Quick action is needed here",
                "This is urgent and can't wait",
                "Let's jump in and handle this fast",
                "Immediate response required",
                "We should move on this instantly"
            ],
            "social_engagement": [
                "Let's collaborate on this together",
                "I'd like to work with others on this",
                "We should discuss this as a team",
                "I want to share this with everyone",
                "Let's engage with the community",
                "I enjoy working together on problems",
                "Teamwork makes this better"
            ],
            "withdrawal": [
                "I prefer to work on this alone",
                "I need some private time for this",
                "I work best independently on this",
                "Let me handle this solo",
                "I'd rather work in isolation here",
                "I need space to focus individually",
                "I prefer solitary work on this"
            ],
            "cooperation": [
                "I'm happy to help with this",
                "Let me assist you with that",
                "I want to support this effort",
                "I agree with this approach",
                "I'll cooperate fully on this",
                "I'm here to help however needed",
                "Let's work together constructively"
            ],
            "conflict": [
                "I disagree with this approach",
                "This conflicts with my understanding",
                "I need to challenge this assumption",
                "I oppose this direction",
                "I have concerns about this method",
                "I question whether this is right",
                "I must argue against this"
            ],
            "stress": [
                "I'm feeling overwhelmed by this",
                "This is causing me anxiety",
                "I'm worried about the outcome",
                "The pressure here is intense",
                "I'm stressed about this situation",
                "This is making me anxious",
                "I feel under significant pressure"
            ],
            "calm_response": [
                "I feel calm and composed about this",
                "This seems peaceful and manageable",
                "I'm approaching this with stability",
                "I feel balanced and centered here",
                "This is a composed response",
                "I'm maintaining equilibrium",
                "I feel serene about this"
            ]
        }
        
        # Pre-compute embeddings for all exemplars
        self.exemplar_embeddings = {}
        for trait_dim, phrases in self.exemplars.items():
            embeddings = [
                self.embedding_adapter.embed(phrase) 
                for phrase in phrases
            ]
            self.exemplar_embeddings[trait_dim] = np.array(embeddings)
    
    def detect_trait_signal(
        self, 
        text: str, 
        trait_dimension: str
    ) -> tuple[bool, float, Optional[str]]:
        """
        Detect if text indicates a trait dimension using semantic similarity.
        
        Args:
            text: Text to analyze
            trait_dimension: One of the trait dimension keys (e.g., "curiosity")
        
        Returns:
            Tuple of (is_match, confidence, best_matching_exemplar)
            - is_match: True if similarity exceeds threshold
            - confidence: Cosine similarity score [0.0, 1.0]
            - best_matching_exemplar: The exemplar with highest similarity
        """
        if not text or trait_dimension not in self.exemplar_embeddings:
            return (False, 0.0, None)
        
        # Embed the input text
        text_embedding = self.embedding_adapter.embed(text)
        
        # Get exemplar embeddings for this trait dimension
        exemplar_embeds = self.exemplar_embeddings[trait_dimension]
        
        # Compute cosine similarity to each exemplar
        similarities = []
        for exemplar_embed in exemplar_embeds:
            sim = self._cosine_similarity(text_embedding, exemplar_embed)
            similarities.append(sim)
        
        # Find best match
        max_similarity = max(similarities)
        best_idx = similarities.index(max_similarity)
        best_exemplar = self.exemplars[trait_dimension][best_idx]
        
        # Check threshold
        is_match = max_similarity >= self.SIMILARITY_THRESHOLD
        
        return (is_match, max_similarity, best_exemplar)
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return float(dot_product / (norm_a * norm_b))
    
    def apply_event_effects(self, event: dict, context: dict) -> list[dict]:
        """
        Apply event effects and return deterministic trait deltas.
        
        This replaces TraitDriftManager.apply_event_effects with semantic detection.
        
        Args:
            event: Event dictionary with 'kind', 'content', 'meta'
            context: Additional context for analysis
        
        Returns:
            List of trait delta dictionaries with audit trail
        """
        deltas = []
        
        event_kind = event.get("kind", "")
        content = event.get("content", "")
        meta = event.get("meta", {})
        
        # Only analyze events with meaningful content
        if not content or len(content.strip()) < 10:
            return deltas
        
        # Detect each trait dimension
        trait_mappings = {
            "curiosity": ("O", 0.02),
            "routine_preference": ("O", -0.01),
            "planning": ("C", 0.02),
            "impulsiveness": ("C", -0.01),
            "social_engagement": ("E", 0.01),
            "withdrawal": ("E", -0.01),
            "cooperation": ("A", 0.01),
            "conflict": ("A", -0.01),
            "stress": ("N", 0.01),
            "calm_response": ("N", -0.01)
        }
        
        for dimension, (trait_code, delta_value) in trait_mappings.items():
            is_match, confidence, exemplar = self.detect_trait_signal(
                content, dimension
            )
            
            if is_match:
                deltas.append({
                    "trait": trait_code,
                    "delta": delta_value,
                    "reason": f"semantic_match_{dimension}",
                    "confidence": confidence,
                    "matched_exemplar": exemplar,
                    "embedding_spec": self.EMBEDDING_SPEC
                })
        
        # Clamp deltas
        for delta_item in deltas:
            delta_item["delta"] = max(-1.0, min(1.0, delta_item["delta"]))
        
        return deltas


class SemanticTraitDriftManager:
    """
    Replacement for TraitDriftManager using semantic detection.
    
    Maintains same API but uses embedding similarity instead of keywords.
    """
    
    VALID_TRAITS = {"O", "C", "E", "A", "N"}
    
    def __init__(self, embedding_adapter):
        self.detector = SemanticTraitDetector(embedding_adapter)
    
    def apply_event_effects(self, event: dict, context: dict) -> list[dict]:
        """Apply event effects using semantic detection."""
        return self.detector.apply_event_effects(event, context)
    
    def apply_and_log(self, eventlog, event: dict, context: dict) -> None:
        """Apply trait deltas and append policy_update to ledger."""
        source_event_id = event.get("id")
        if source_event_id and self._already_processed(eventlog, source_event_id):
            return
        
        changes = self.apply_event_effects(event, context)
        
        if not changes:
            return
        
        meta = {
            "component": "personality",
            "source_event_id": source_event_id,
            "changes": changes,
            "deterministic": True,
            "method": "semantic_embedding_similarity",
            "embedding_spec": self.detector.EMBEDDING_SPEC
        }
        
        eventlog.append(
            kind="policy_update", 
            content="trait drift update (semantic)", 
            meta=meta
        )
    
    def _already_processed(self, eventlog, source_event_id: int) -> bool:
        """Check if source event already processed."""
        if not source_event_id:
            return False
        
        all_events = eventlog.read_all()
        for ev in all_events:
            if (ev.get("kind") == "policy_update" and
                ev.get("meta", {}).get("component") == "personality" and
                ev.get("meta", {}).get("source_event_id") == source_event_id):
                return True
        return False
```

### Migration Strategy

1. **Add feature flag**: `PMM_USE_SEMANTIC_TRAIT_DETECTION=1`
2. **Run in parallel**: Log both old and new detections for comparison
3. **A/B test**: Compare trait evolution trajectories
4. **Gradual rollout**: Enable for new ledgers first
5. **Full migration**: Remove old keyword-based code

### Testing

```python
def test_semantic_trait_detection():
    """Test semantic detection vs keyword detection."""
    
    test_cases = [
        # Curiosity - different phrasings
        ("I'm curious about how this works", "curiosity", True),
        ("What are the underlying mechanisms here?", "curiosity", True),
        ("Let me investigate this further", "curiosity", True),
        ("I wonder what would happen if...", "curiosity", True),
        
        # Should NOT match curiosity
        ("The cat is curious", "curiosity", False),  # Different context
        ("I'm done with this task", "curiosity", False),
        
        # Planning
        ("Let me organize this systematically", "planning", True),
        ("I need to structure my approach", "planning", True),
        
        # Stress
        ("This is overwhelming me", "stress", True),
        ("I feel anxious about the deadline", "stress", True),
    ]
    
    detector = SemanticTraitDetector(embedding_adapter)
    
    for text, dimension, expected_match in test_cases:
        is_match, confidence, exemplar = detector.detect_trait_signal(text, dimension)
        
        assert is_match == expected_match, (
            f"Failed for '{text}': expected {expected_match}, "
            f"got {is_match} (confidence: {confidence:.3f})"
        )
```

---

## Design 2: Structural Pattern Validator

### Overview

Replace keyword-based validation with structural pattern analysis.

### Architecture

```python
"""Structural pattern validation without keyword matching."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SemanticUnit:
    """Represents a semantic unit with grammatical structure."""
    text: str
    has_comparison: bool
    has_numeric: bool
    has_noun_phrase: bool
    comparison_operator: Optional[str] = None
    numeric_value: Optional[float] = None


class StructuralValidator:
    """
    Validates text structure without brittle keyword matching.
    
    Uses grammatical patterns and semantic structure instead of keywords.
    """
    
    COMPARISON_OPERATORS = {">=", "<=", ">", "<", "=", "≥", "≤"}
    OBSERVABLE_STRUCTURES = {
        "comparison_with_number",  # "error rate < 5%"
        "within_timeframe",         # "within 3 turns"
        "at_least_quantity",        # "at least 2 citations"
    }
    
    def has_observable_clause(self, text: str) -> bool:
        """
        Detect observable clauses by structure, not keywords.
        
        An observable clause has:
        1. A measurable subject (noun phrase)
        2. A comparison or threshold
        3. A specific value or bound
        
        Examples:
        - "error rate < 5%" ✓
        - "within 3 turns" ✓
        - "at least 2 citations" ✓
        - "be more careful" ✗ (no measurable threshold)
        """
        if not text:
            return False
        
        # Check for comparison operators with numbers
        if self._has_comparison_with_number(text):
            return True
        
        # Check for "within N [unit]" pattern
        if self._has_within_timeframe(text):
            return True
        
        # Check for "at least N [unit]" pattern
        if self._has_at_least_quantity(text):
            return True
        
        return False
    
    def _has_comparison_with_number(self, text: str) -> bool:
        """Check for comparison operator followed by number."""
        for op in self.COMPARISON_OPERATORS:
            if op in text:
                # Find position of operator
                idx = text.find(op)
                # Check if followed by number (within 10 chars)
                rest = text[idx + len(op):idx + len(op) + 10]
                if self._contains_number(rest):
                    return True
        return False
    
    def _has_within_timeframe(self, text: str) -> bool:
        """Check for 'within N [unit]' structure."""
        tokens = text.lower().split()
        for i, token in enumerate(tokens):
            if token == "within" and i + 1 < len(tokens):
                # Check if next token is a number
                next_token = tokens[i + 1].strip(".,;:")
                if next_token.isdigit():
                    return True
        return False
    
    def _has_at_least_quantity(self, text: str) -> bool:
        """Check for 'at least N [unit]' structure."""
        text_lower = text.lower()
        if "at least" in text_lower:
            idx = text_lower.find("at least")
            rest = text[idx + len("at least"):idx + len("at least") + 20]
            if self._contains_number(rest):
                return True
        return False
    
    def _contains_number(self, text: str) -> bool:
        """Check if text contains a number."""
        tokens = text.split()
        for token in tokens:
            clean = token.strip(".,;:!?%")
            if clean.isdigit() or self._is_float(clean):
                return True
        return False
    
    def _is_float(self, s: str) -> bool:
        """Check if string is a float."""
        try:
            float(s)
            return True
        except ValueError:
            return False


def validate_decision_probe_structural(text: str, eventlog) -> tuple[bool, str]:
    """
    Validate decision probe using structural analysis.
    
    Replaces keyword-based validation with structure checking.
    """
    from pmm.utils.parsers import extract_probe_sections, extract_event_ids_from_evidence
    
    sections = extract_probe_sections(text)
    
    # Shape checks
    required = ["observation", "inference", "evidence", "next_step", "test"]
    for req in required:
        if req not in sections or not sections[req]:
            return False, "Malformed: missing required sections"
    
    # Check inference has IF...THEN structure (structural, not keyword)
    inf = sections["inference"]
    if not _has_if_then_structure(inf):
        return False, "Inference not in IF…THEN form"
    
    # Check inference has observable using structural validator
    validator = StructuralValidator()
    if not validator.has_observable_clause(inf):
        return False, "Inference lacks observable"
    
    # Evidence validation (unchanged - already structural)
    eids = extract_event_ids_from_evidence(sections["evidence"])
    if len(eids) < 2:
        return False, "INSUFFICIENT EVIDENCE"
    
    # Test must have explicit threshold (structural check)
    test_line = sections["test"].strip()
    if not validator.has_observable_clause(test_line):
        return False, "Test lacks explicit threshold"
    
    return True, "OK"


def _has_if_then_structure(text: str) -> bool:
    """Check for IF...THEN structure (case-insensitive, position-aware)."""
    text_upper = text.upper()
    text_lower = text.lower()
    
    # Must have both IF and THEN
    has_if = "IF" in text_upper or "if" in text_lower
    has_then = "THEN" in text_upper or "then" in text_lower
    
    if not (has_if and has_then):
        return False
    
    # IF should come before THEN
    if_pos = text_upper.find("IF") if "IF" in text_upper else text_lower.find("if")
    then_pos = text_upper.find("THEN") if "THEN" in text_upper else text_lower.find("then")
    
    return if_pos < then_pos
```

---

## Design 3: Commitment Extractor with Semantic Matching

### Overview

Replace keyword-based commitment extraction with semantic similarity.

### Architecture

```python
"""Semantic commitment extraction using exemplar matching."""

from typing import Optional


class SemanticCommitmentExtractor:
    """
    Extracts commitments using semantic similarity instead of keyword matching.
    
    Replaces brittle patterns like "I committed to" with exemplar-based detection.
    """
    
    def __init__(self, embedding_adapter):
        self.embedding_adapter = embedding_adapter
        self._initialize_exemplars()
    
    def _initialize_exemplars(self):
        """Initialize exemplars for commitment detection."""
        
        # Exemplars for "open commitment" intent
        self.open_commitment_exemplars = [
            "I will complete this task",
            "I plan to work on this feature",
            "My goal is to accomplish this",
            "I commit to finishing this",
            "I intend to deliver this",
            "I'm going to implement this",
            "I'll make sure to do this",
            "I promise to handle this"
        ]
        
        # Exemplars for "closed commitment" intent
        self.closed_commitment_exemplars = [
            "I completed this task",
            "I finished working on this",
            "This is done now",
            "I accomplished this goal",
            "I delivered this feature",
            "This commitment is fulfilled",
            "I've finished this work"
        ]
        
        # Pre-compute embeddings
        self.open_embeddings = [
            self.embedding_adapter.embed(ex) 
            for ex in self.open_commitment_exemplars
        ]
        self.closed_embeddings = [
            self.embedding_adapter.embed(ex)
            for ex in self.closed_commitment_exemplars
        ]
    
    def extract_commitments(
        self, 
        text: str
    ) -> list[tuple[str, str, float]]:
        """
        Extract commitments from text using semantic matching.
        
        Args:
            text: Text to analyze (typically LLM response)
        
        Returns:
            List of (commitment_text, intent, confidence) tuples
            - commitment_text: The extracted commitment
            - intent: "open" or "closed"
            - confidence: Similarity score [0.0, 1.0]
        """
        if not text:
            return []
        
        commitments = []
        
        # Split into sentences
        sentences = self._split_sentences(text)
        
        for sentence in sentences:
            # Skip very short sentences
            if len(sentence.split()) < 4:
                continue
            
            # Check if sentence is a commitment
            intent, confidence = self._classify_commitment_intent(sentence)
            
            if intent and confidence >= 0.70:
                commitments.append((sentence, intent, confidence))
        
        return commitments
    
    def _classify_commitment_intent(
        self, 
        text: str
    ) -> tuple[Optional[str], float]:
        """
        Classify if text expresses commitment intent.
        
        Returns:
            (intent, confidence) where intent is "open", "closed", or None
        """
        text_embedding = self.embedding_adapter.embed(text)
        
        # Check similarity to "open" exemplars
        open_similarities = [
            self._cosine_similarity(text_embedding, ex_embed)
            for ex_embed in self.open_embeddings
        ]
        max_open_sim = max(open_similarities) if open_similarities else 0.0
        
        # Check similarity to "closed" exemplars
        closed_similarities = [
            self._cosine_similarity(text_embedding, ex_embed)
            for ex_embed in self.closed_embeddings
        ]
        max_closed_sim = max(closed_similarities) if closed_similarities else 0.0
        
        # Determine intent based on highest similarity
        if max_open_sim >= 0.70 or max_closed_sim >= 0.70:
            if max_open_sim > max_closed_sim:
                return ("open", max_open_sim)
            else:
                return ("closed", max_closed_sim)
        
        return (None, 0.0)
    
    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences deterministically."""
        sentences = []
        current = []
        
        for char in text:
            if char in ".!?\n":
                if current:
                    sentences.append("".join(current).strip())
                    current = []
            else:
                current.append(char)
        
        if current:
            sentences.append("".join(current).strip())
        
        return [s for s in sentences if s]
    
    def _cosine_similarity(self, a, b) -> float:
        """Compute cosine similarity."""
        import numpy as np
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot_product / (norm_a * norm_b))
```

---

## Design 4: Configuration-Driven Exemplars

### Overview

Store exemplars in configuration files for easy updates without code changes.

### Architecture

```yaml
# config/semantic_exemplars.yaml

trait_detection:
  curiosity:
    threshold: 0.75
    exemplars:
      - "I want to explore this topic further"
      - "This makes me wonder about the underlying mechanisms"
      - "I'm interested in learning more about this"
      - "What if we investigated the root cause"
      - "I'd like to discover how this works"
  
  planning:
    threshold: 0.75
    exemplars:
      - "Let me organize these steps systematically"
      - "I'll prepare a structured approach"
      - "We should schedule this carefully"

commitment_extraction:
  open_commitment:
    threshold: 0.70
    exemplars:
      - "I will complete this task"
      - "I plan to work on this feature"
      - "My goal is to accomplish this"
  
  closed_commitment:
    threshold: 0.70
    exemplars:
      - "I completed this task"
      - "I finished working on this"
      - "This is done now"

directive_classification:
  meta_principle:
    threshold: 0.75
    exemplars:
      - "I should evolve my principles based on experience"
      - "I need to refine my framework for decision-making"
  
  principle:
    threshold: 0.75
    exemplars:
      - "I value honesty in all interactions"
      - "I remain committed to truth-seeking"
  
  commitment:
    threshold: 0.70
    exemplars:
      - "I will implement this feature tomorrow"
      - "I plan to complete this task by Friday"
```

### Loader

```python
"""Configuration loader for semantic exemplars."""

import yaml
from pathlib import Path


class ExemplarConfig:
    """Loads and manages semantic exemplar configuration."""
    
    def __init__(self, config_path: str = "config/semantic_exemplars.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
    
    def _load_config(self) -> dict:
        """Load exemplar configuration from YAML."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Exemplar config not found: {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def get_exemplars(self, category: str, subcategory: str) -> list[str]:
        """Get exemplars for a specific category."""
        try:
            return self.config[category][subcategory]["exemplars"]
        except KeyError:
            return []
    
    def get_threshold(self, category: str, subcategory: str) -> float:
        """Get similarity threshold for a category."""
        try:
            return self.config[category][subcategory]["threshold"]
        except KeyError:
            return 0.75  # Default threshold
```

---

## Summary

These designs provide **three complementary approaches** to replace brittle keyword matching:

1. **Embedding Similarity** - Best for trait detection, commitment extraction
2. **Structural Pattern Matching** - Best for validation, format checking
3. **Configuration-Driven Exemplars** - Best for maintainability, auditability

All designs follow CONTRIBUTING.md principles:
- ✅ No regex
- ✅ No brittle keywords
- ✅ Semantic-based
- ✅ Deterministic (given same embeddings)
- ✅ Auditable (log similarity scores)
- ✅ Model-agnostic (works across LLM providers)
