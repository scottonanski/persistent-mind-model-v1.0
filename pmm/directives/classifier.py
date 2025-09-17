from typing import Dict, Any, Optional, List, Tuple
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

    # ---- Identity intent classification -------------------------------------------------

    def classify_identity_intent(
        self,
        text: str,
        speaker: str,
        recent_events: List[Dict],
    ) -> Tuple[str, Optional[str], float]:
        """Return (intent, candidate_name, confidence)."""

        raw = (text or "").strip()
        if not raw:
            return ("irrelevant", None, 0.0)

        words_raw = raw.split()
        words_lower = [w.lower() for w in words_raw]

        features = self._extract_naming_features(
            raw, words_raw, words_lower, speaker, recent_events
        )
        intent, name, confidence = self._classify_naming_intent(
            raw, words_raw, words_lower, features, speaker
        )

        if self.eventlog:
            try:
                self.eventlog.append(
                    kind="naming_intent_classified",
                    content=raw,
                    meta={
                        "intent": intent,
                        "name": name,
                        "confidence": float(confidence),
                        "speaker": speaker,
                        "features": {
                            "has_naming_context": features["has_naming_context"],
                            "subject_role": features["subject_role"],
                            "has_proper_noun": features["has_proper_noun"],
                            "has_linking_verb": features["has_linking_verb"],
                        },
                    },
                )
            except Exception:
                logger.exception("Failed to log naming intent classification")

        return intent, name, confidence

    def _extract_naming_features(
        self,
        text: str,
        words_raw: List[str],
        words_lower: List[str],
        speaker: str,
        recent_events: List[Dict],
    ) -> Dict[str, Any]:
        features: Dict[str, Any] = {
            "has_naming_context": False,
            "subject_role": None,
            "has_proper_noun": False,
            "has_linking_verb": False,
        }

        # Context from recent events
        naming_tokens = {"name", "call", "rename", "dub"}
        for ev in recent_events[-3:]:
            if ev.get("kind") in {"user", "response"}:
                content = str(ev.get("content", "")).lower()
                if any(tok in content for tok in naming_tokens):
                    features["has_naming_context"] = True
                    break

        if "name" in words_lower or "call" in words_lower:
            features["has_naming_context"] = True

        if words_lower:
            first = words_lower[0]
            if first in {"you", "your"}:
                features["subject_role"] = "assistant"
            elif first in {"i", "i'm", "i’m", "my"}:
                features["subject_role"] = speaker

        if "your name" in text.lower() or "call you" in text.lower():
            features["subject_role"] = "assistant"
        elif "my name" in text.lower() and speaker == "user":
            features["subject_role"] = "user"

        linking_verbs = {"am", "'m", "’m", "is", "are", "be", "called"}
        features["has_linking_verb"] = any(w in linking_verbs for w in words_lower)

        common_words = {
            "i",
            "i'm",
            "i’m",
            "you",
            "your",
            "the",
            "a",
            "an",
        }
        for token in words_raw[1:]:
            cleaned = token.strip(".,!?;:")
            if (
                len(cleaned) > 1
                and cleaned[0].isupper()
                and cleaned.lower() not in common_words
            ):
                features["has_proper_noun"] = True
                break

        return features

    def _classify_naming_intent(
        self,
        text: str,
        words_raw: List[str],
        words_lower: List[str],
        features: Dict[str, Any],
        speaker: str = "user",
    ) -> Tuple[str, Optional[str], float]:
        score = 0.0
        if features["has_naming_context"]:
            score += 0.4
        if features["has_linking_verb"]:
            score += 0.3
        if features["has_proper_noun"]:
            score += 0.2
        if features["subject_role"] == "assistant":
            score += 0.3
        elif features["subject_role"] == "user":
            score += 0.1

        candidate = None
        intent = "irrelevant"

        # Check for assistant self-affirmation first (speaker is assistant + "I am")
        if (
            features["subject_role"] == "assistant"
            and "i am" in text.lower()
            and speaker == "assistant"
        ):
            intent = "affirm_assistant_name"
            candidate = self._extract_candidate_name(words_raw, words_lower)
        elif (
            features["subject_role"] == "assistant"
            and features["has_proper_noun"]
            and score >= 0.6
        ):
            intent = "assign_assistant_name"
            candidate = self._extract_candidate_name(words_raw, words_lower)
        elif (
            features["subject_role"] == "assistant"
            and not features["has_proper_noun"]
            and score >= 0.6
        ):
            intent = "assign_assistant_name"
        elif features["subject_role"] == "user" and score >= 0.6:
            intent = "assign_user_name"

        return intent, candidate, min(score, 1.0)

    def _extract_candidate_name(
        self, words_raw: List[str], words_lower: List[str]
    ) -> Optional[str]:
        # Look for names after linking verbs
        linking_verbs = {"is", "are", "am", "'m", "'m", "called"}

        for i, word_lower in enumerate(words_lower):
            if word_lower in linking_verbs and i + 1 < len(words_raw):
                next_word = words_raw[i + 1].strip(".,!?;:")
                if len(next_word) > 1 and next_word[0].isupper():
                    # Filter out common words that aren't names
                    if next_word.lower() not in {
                        "important",
                        "critical",
                        "urgent",
                        "great",
                        "good",
                        "bad",
                    }:
                        return next_word

        # Look for "call you/call them X" pattern
        for i, word_lower in enumerate(words_lower):
            if word_lower == "call" and i + 1 < len(words_lower):
                if words_lower[i + 1] in {"you", "them", "him", "her"} and i + 2 < len(
                    words_raw
                ):
                    candidate = words_raw[i + 2].strip(".,!?;:")
                    if len(candidate) > 1 and candidate[0].isupper():
                        if candidate.lower() not in {
                            "important",
                            "critical",
                            "urgent",
                            "great",
                            "good",
                            "bad",
                        }:
                            return candidate

        # Look for "name is X" or "name you X" patterns
        for i, word_lower in enumerate(words_lower):
            if word_lower == "name":
                # Check "name is X"
                if (
                    i + 1 < len(words_lower)
                    and words_lower[i + 1] == "is"
                    and i + 2 < len(words_raw)
                ):
                    candidate = words_raw[i + 2].strip(".,!?;:")
                    if len(candidate) > 1 and candidate[0].isupper():
                        if candidate.lower() not in {
                            "important",
                            "critical",
                            "urgent",
                            "great",
                            "good",
                            "bad",
                        }:
                            return candidate
                # Check "name you X"
                elif (
                    i + 1 < len(words_lower)
                    and words_lower[i + 1] == "you"
                    and i + 2 < len(words_raw)
                ):
                    candidate = words_raw[i + 2].strip(".,!?;:")
                    if len(candidate) > 1 and candidate[0].isupper():
                        if candidate.lower() not in {
                            "important",
                            "critical",
                            "urgent",
                            "great",
                            "good",
                            "bad",
                        }:
                            return candidate

        return None

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
