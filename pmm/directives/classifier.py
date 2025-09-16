from typing import Dict, Any, Optional, List
import logging
from dataclasses import dataclass

try:
    from pmm.storage.eventlog import EventLog
except ImportError:
    EventLog = None

logger = logging.getLogger(__name__)


@dataclass
class DirectiveFeatures:
    """Semantic features extracted from directive text."""

    # Temporal scope indicators
    temporal_scope: str  # "immediate", "ongoing", "evolutionary"

    # Abstraction level
    abstraction_level: str  # "concrete", "conceptual", "meta"

    # Agency indicators
    agency_type: str  # "behavioral", "identity", "framework"

    # Semantic density (concepts per word)
    semantic_density: float

    # Self-reference patterns
    self_reference_type: str  # "action", "identity", "evolution"


class SemanticDirectiveClassifier:
    """
    Classifies directives using semantic analysis rather than keyword matching.
    Learns from the AI's natural language patterns to distinguish between:
    - Meta-principles: Rules about how to evolve rules
    - Principles: Identity-defining guidelines
    - Commitments: Specific behavioral intentions
    """

    def __init__(self, eventlog: Optional["EventLog"] = None):
        self.classification_history: Dict[str, str] = {}
        self.eventlog = eventlog  # Store EventLog instance for logging

    def extract_features(self, text: str) -> DirectiveFeatures:
        """Extract semantic features from directive text."""
        text_lower = text.lower().strip()
        words = text_lower.split()

        # Analyze temporal scope
        temporal_scope = self._analyze_temporal_scope(text_lower, words)

        # Analyze abstraction level
        abstraction_level = self._analyze_abstraction_level(text_lower, words)

        # Analyze agency type
        agency_type = self._analyze_agency_type(text_lower, words)

        # Calculate semantic density
        semantic_density = self._calculate_semantic_density(text_lower, words)

        # Analyze self-reference patterns
        self_reference_type = self._analyze_self_reference(text_lower, words)

        return DirectiveFeatures(
            temporal_scope=temporal_scope,
            abstraction_level=abstraction_level,
            agency_type=agency_type,
            semantic_density=semantic_density,
            self_reference_type=self_reference_type,
        )

    def _analyze_temporal_scope(self, text: str, words: List[str]) -> str:
        """Determine temporal scope from linguistic patterns."""

        # Immediate scope indicators (specific actions)
        immediate_indicators = {
            "verbs": ["will", "plan", "intend", "aim", "commit"],
            "time_refs": ["today", "tomorrow", "next", "soon", "immediately"],
            "specificity": ["specific", "particular", "concrete", "exact"],
        }

        # Ongoing scope indicators (continuous states)
        ongoing_indicators = {
            "continuity": ["always", "continuously", "ongoing", "maintain", "sustain"],
            "identity": ["am", "being", "remain", "stay", "keep"],
            "principles": ["principle", "rule", "guideline", "standard", "value"],
        }

        # Evolutionary scope indicators (meta-level change)
        evolutionary_indicators = {
            "change": ["evolve", "develop", "grow", "adapt", "transform"],
            "meta": ["combine", "synthesize", "integrate", "refine", "improve"],
            "reflection": ["reflect", "consider", "evaluate", "assess", "review"],
        }

        # Score each category
        immediate_score = self._score_indicators(text, words, immediate_indicators)
        ongoing_score = self._score_indicators(text, words, ongoing_indicators)
        evolutionary_score = self._score_indicators(
            text, words, evolutionary_indicators
        )

        # Return highest scoring category
        scores = {
            "immediate": immediate_score,
            "ongoing": ongoing_score,
            "evolutionary": evolutionary_score,
        }

        return max(scores.items(), key=lambda x: x[1])[0]

    def _analyze_abstraction_level(self, text: str, words: List[str]) -> str:
        """Determine abstraction level from concept density and specificity."""

        # Concrete indicators (specific actions/objects)
        concrete_indicators = {
            "actions": ["write", "create", "build", "send", "call", "meet"],
            "objects": ["document", "file", "message", "report", "task"],
            "specificity": ["specific", "particular", "exact", "precise", "detailed"],
        }

        # Conceptual indicators (ideas/states)
        conceptual_indicators = {
            "concepts": ["truth", "respect", "integrity", "empathy", "growth"],
            "states": ["honest", "transparent", "supportive", "constructive"],
            "qualities": ["quality", "approach", "manner", "way", "style"],
        }

        # Meta indicators (concepts about concepts)
        meta_indicators = {
            "meta_concepts": ["principle", "framework", "system", "approach", "method"],
            "self_reference": [
                "my own",
                "my approach",
                "my framework",
                "my principles",
            ],
            "evolution": ["evolve", "develop", "refine", "improve", "adapt"],
        }

        concrete_score = self._score_indicators(text, words, concrete_indicators)
        conceptual_score = self._score_indicators(text, words, conceptual_indicators)
        meta_score = self._score_indicators(text, words, meta_indicators)

        scores = {
            "concrete": concrete_score,
            "conceptual": conceptual_score,
            "meta": meta_score,
        }

        return max(scores.items(), key=lambda x: x[1])[0]

    def _analyze_agency_type(self, text: str, words: List[str]) -> str:
        """Determine type of agency being expressed."""

        # Behavioral agency (doing things)
        behavioral_indicators = {
            "actions": ["do", "perform", "execute", "carry out", "implement"],
            "behaviors": [
                "respond",
                "interact",
                "communicate",
                "engage",
                "participate",
            ],
            "outcomes": ["achieve", "accomplish", "complete", "deliver", "produce"],
        }

        # Identity agency (being something)
        identity_indicators = {
            "being": ["am", "being", "remain", "stay", "become"],
            "characteristics": ["honest", "respectful", "supportive", "constructive"],
            "roles": ["assistant", "helper", "guide", "supporter", "partner"],
        }

        # Framework agency (changing how I operate)
        framework_indicators = {
            "systems": ["framework", "approach", "method", "system", "process"],
            "evolution": ["evolve", "develop", "refine", "improve", "adapt"],
            "meta": ["combine", "synthesize", "integrate", "organize", "structure"],
        }

        behavioral_score = self._score_indicators(text, words, behavioral_indicators)
        identity_score = self._score_indicators(text, words, identity_indicators)
        framework_score = self._score_indicators(text, words, framework_indicators)

        scores = {
            "behavioral": behavioral_score,
            "identity": identity_score,
            "framework": framework_score,
        }

        return max(scores.items(), key=lambda x: x[1])[0]

    def _calculate_semantic_density(self, text: str, words: List[str]) -> float:
        """Calculate semantic density (abstract concepts per word)."""
        if not words:
            return 0.0

        # Count abstract/conceptual words
        abstract_words = {
            "truth",
            "respect",
            "integrity",
            "empathy",
            "growth",
            "principle",
            "framework",
            "approach",
            "method",
            "system",
            "evolution",
            "development",
            "understanding",
            "awareness",
            "consciousness",
            "reflection",
            "insight",
        }

        abstract_count = sum(1 for word in words if word in abstract_words)
        return abstract_count / len(words)

    def _analyze_self_reference(self, text: str, words: List[str]) -> str:
        """Analyze how the AI refers to itself."""

        # Action self-reference (I will do X)
        if any(
            pattern in text for pattern in ["i will", "i plan", "i intend", "i commit"]
        ):
            return "action"

        # Identity self-reference (I am X)
        if any(
            pattern in text
            for pattern in ["i am", "i remain", "i acknowledge", "my approach"]
        ):
            return "identity"

        # Evolution self-reference (I evolve X)
        if any(
            pattern in text
            for pattern in ["i evolve", "i develop", "i refine", "i combine"]
        ):
            return "evolution"

        return "none"

    def _score_indicators(
        self, text: str, words: List[str], indicators: Dict[str, List[str]]
    ) -> float:
        """Score text against indicator categories."""
        total_score = 0.0
        total_possible = 0

        for category, indicator_list in indicators.items():
            category_score = 0
            for indicator in indicator_list:
                if indicator in text:
                    category_score += 1
                total_possible += 1
            total_score += category_score

        return total_score / total_possible if total_possible > 0 else 0.0

    def classify_directive(self, text: str) -> Dict[str, Any]:
        """
        Classify a directive text into a type and associated metadata.

        Args:
            text: The text of the directive to classify.

        Returns:
            A dictionary with classification results including type and confidence.
        """
        features = self.extract_features(text)

        # Classification logic based on feature combinations

        # Meta-principles: evolutionary + meta + framework
        if (
            features.temporal_scope == "evolutionary"
            and features.abstraction_level == "meta"
            and features.agency_type == "framework"
        ):
            classification = "meta-principle"

        # Principles: ongoing + conceptual + identity
        elif (
            features.temporal_scope == "ongoing"
            and features.abstraction_level in ["conceptual", "meta"]
            and features.agency_type == "identity"
        ):
            classification = "principle"

        # High semantic density also suggests principle
        elif features.semantic_density > 0.3:
            classification = "principle"

        # Default to commitment for behavioral/immediate directives
        else:
            classification = "commitment"

        # Store for learning
        self.classification_history[text] = classification

        # Log classification result to EventLog if available
        if self.eventlog:
            self.eventlog.append(
                kind="directive_classified",
                content=text,
                meta={
                    "type": classification,
                    "features": {
                        "temporal_scope": features.temporal_scope,
                        "abstraction_level": features.abstraction_level,
                        "agency_type": features.agency_type,
                        "semantic_density": features.semantic_density,
                        "self_reference_type": features.self_reference_type,
                    },
                },
            )

        return {
            "type": classification,
            "confidence": self.get_classification_confidence(text),
            "text": text,
        }

    def get_classification_confidence(self, text: str) -> float:
        """Return confidence scores for each classification."""
        features = self.extract_features(text)

        # Calculate confidence for each type based on feature alignment
        meta_confidence = 0.0
        if features.temporal_scope == "evolutionary":
            meta_confidence += 0.4
        if features.abstraction_level == "meta":
            meta_confidence += 0.4
        if features.agency_type == "framework":
            meta_confidence += 0.2

        principle_confidence = 0.0
        if features.temporal_scope == "ongoing":
            principle_confidence += 0.3
        if features.abstraction_level in ["conceptual", "meta"]:
            principle_confidence += 0.3
        if features.agency_type == "identity":
            principle_confidence += 0.2
        if features.semantic_density > 0.3:
            principle_confidence += 0.2

        commitment_confidence = 0.0
        if features.temporal_scope == "immediate":
            commitment_confidence += 0.4
        if features.abstraction_level == "concrete":
            commitment_confidence += 0.3
        if features.agency_type == "behavioral":
            commitment_confidence += 0.3

        # Normalize to sum to 1.0
        total = meta_confidence + principle_confidence + commitment_confidence
        if total > 0:
            return {
                "meta-principle": meta_confidence / total,
                "principle": principle_confidence / total,
                "commitment": commitment_confidence / total,
            }
        else:
            return {"meta-principle": 0.33, "principle": 0.33, "commitment": 0.34}

    def learn_from_feedback(self, text: str, correct_classification: str):
        """Learn from classification corrections (future enhancement)."""
        # This would update internal weights based on feedback; for now store the correction
        self.classification_history[text] = correct_classification
