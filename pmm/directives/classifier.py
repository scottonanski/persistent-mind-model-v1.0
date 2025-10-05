import logging
from dataclasses import dataclass
from typing import Any, Optional

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
        self.classification_history: dict[str, str] = {}
        self.eventlog = eventlog  # Store EventLog instance for logging

    # ---- Identity intent classification -------------------------------------------------

    def classify_identity_intent(
        self,
        text: str,
        speaker: str,
        recent_events: list[dict],
    ) -> tuple[str, str | None, float]:
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
                            "has_proper_noun": features["has_proper_noun"],
                            "proper_noun_count": features["proper_noun_count"],
                            "proper_nouns": features.get("proper_nouns", []),
                        },
                    },
                )
            except Exception:
                logger.exception("Failed to log naming intent classification")

        return intent, name, confidence

    def _extract_naming_features(
        self,
        text: str,
        words_raw: list[str],
        words_lower: list[str],
        speaker: str,
        recent_events: list[dict],
    ) -> dict[str, Any]:
        """Extract deterministic features indicating a user naming directive.

        Relies on positional heuristics (proper nouns after second-person references
        or near naming verbs). Avoids specific phrase lists so behavior remains
        language-flexible and audit-friendly.
        """

        features: dict[str, Any] = {
            "has_proper_noun": False,
            "proper_noun_count": 0,
            "proper_nouns": [],
            "proper_positions": [],
            "second_person_positions": [],
            "naming_verb_positions": [],
            "candidate_name": None,
        }

        second_person_tokens = {"you", "your", "yours", "yourself", "yourselves"}
        naming_verbs = {"name", "call", "rename", "dub", "christen"}

        common_words = {
            "i",
            "you",
            "the",
            "a",
            "an",
            "this",
            "that",
            "these",
            "those",
            "my",
            "your",
            "his",
            "her",
            "its",
            "our",
            "their",
        }

        for index, token in enumerate(words_lower):
            raw_token = words_raw[index]
            if token in second_person_tokens:
                features["second_person_positions"].append(index)
            if token in naming_verbs:
                features["naming_verb_positions"].append(index)

            # Skip sentence-initial capitalisation bias by ignoring first token
            if index == 0:
                continue

            cleaned = raw_token.strip(".,!?;:\"'()[]{}<>")
            if (
                len(cleaned) > 1
                and cleaned[0].isupper()
                and cleaned.lower() not in common_words
            ):
                features["proper_nouns"].append(cleaned)
                features["proper_positions"].append(index)

        features["has_proper_noun"] = bool(features["proper_nouns"])
        features["proper_noun_count"] = len(features["proper_nouns"])

        candidate = self._select_candidate_name(features)
        if candidate:
            features["candidate_name"] = candidate

        return features

    def _classify_naming_intent(
        self,
        text: str,
        words_raw: list[str],
        words_lower: list[str],
        features: dict[str, Any],
        speaker: str = "user",
    ) -> tuple[str, str | None, float]:
        """Classify naming intent using positional heuristics."""

        candidate = features.get("candidate_name")
        text_lower = text.lower()

        # Check for user self-identification (e.g., "I'm Scott", "My name is Scott")
        if speaker == "user" and candidate:
            # User introducing themselves
            user_intro_patterns = [
                " i'm ",
                " i am ",
                " my name is ",
                " my name's ",
                " call me ",
            ]

            if any(pattern in f" {text_lower} " for pattern in user_intro_patterns):
                # This is the user telling us their name, not naming the assistant
                return "user_self_identification", candidate, 0.9

            # User naming the assistant
            has_naming_verb = bool(features.get("naming_verb_positions"))
            has_second_person = bool(features.get("second_person_positions"))

            # Confidence scales with contextual evidence
            confidence = 0.9 if has_naming_verb else 0.75
            if has_naming_verb and has_second_person:
                confidence = 0.95
            elif not has_naming_verb and not has_second_person:
                confidence = 0.7

            return "assign_assistant_name", candidate, confidence

        # Assistant self-identification still honoured
        if (
            speaker == "assistant"
            and features["has_proper_noun"]
            and " i am " in f" {text_lower} "
        ):
            # Choose first proper noun after "i am" if present
            candidate = self._candidate_after_phrase("i am", words_lower, features)
            if not candidate and features["proper_nouns"]:
                candidate = features["proper_nouns"][0]
            return "affirm_assistant_name", candidate, 0.8 if candidate else 0.6

        return "irrelevant", None, 0.0

    def _candidate_after_phrase(
        self, phrase: str, words_lower: list[str], features: dict[str, Any]
    ) -> str | None:
        try:
            phrase_tokens = phrase.split()
            for idx in range(len(words_lower) - len(phrase_tokens)):
                if words_lower[idx : idx + len(phrase_tokens)] == phrase_tokens:
                    for pos, name in zip(
                        features["proper_positions"], features["proper_nouns"]
                    ):
                        if pos > idx + len(phrase_tokens) - 1:
                            return name
        except Exception:
            return None
        return None

    def _select_candidate_name(self, features: dict[str, Any]) -> str | None:
        """Choose a candidate name based on positional heuristics."""

        proper_positions = features.get("proper_positions", [])
        proper_nouns = features.get("proper_nouns", [])
        if not proper_positions:
            return None

        second_positions = features.get("second_person_positions", [])
        verb_positions = features.get("naming_verb_positions", [])

        # Prefer nouns that appear shortly after a naming verb
        for verb_index in verb_positions:
            window_limit = verb_index + 4
            for pos, name in zip(proper_positions, proper_nouns):
                if verb_index < pos <= window_limit:
                    return name

        # Otherwise, require the noun appear after a second-person reference
        for pos, name in zip(proper_positions, proper_nouns):
            if any(sp < pos for sp in second_positions):
                return name

        # As final fallback, allow single proper noun if the message directly addresses the assistant
        if len(proper_nouns) == 1 and (second_positions or verb_positions):
            return proper_nouns[0]

        # Also allow single proper noun for simple self-identification (e.g., "I'm Scott")
        # This will be filtered by intent classification to distinguish user vs assistant naming
        if len(proper_nouns) == 1:
            return proper_nouns[0]

        return None

    # _extract_candidate_name removed - proper nouns now extracted in _extract_naming_features

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

    def _analyze_temporal_scope(self, text: str, words: list[str]) -> str:
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

    def _analyze_abstraction_level(self, text: str, words: list[str]) -> str:
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

    def _analyze_agency_type(self, text: str, words: list[str]) -> str:
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

    def _calculate_semantic_density(self, text: str, words: list[str]) -> float:
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

    def _analyze_self_reference(self, text: str, words: list[str]) -> str:
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
        self, text: str, words: list[str], indicators: dict[str, list[str]]
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

    def classify_directive(self, text: str) -> dict[str, Any]:
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
