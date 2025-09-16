import logging
from typing import Optional, List

try:
    from pmm.storage.eventlog import EventLog
    from pmm.config import COMMITMENT_THRESHOLD
except ImportError:
    EventLog = None
    COMMITMENT_THRESHOLD = 0.7

logger = logging.getLogger(__name__)


class CommitmentExtractor:
    """
    Extracts commitments from text using semantic and structural analysis.
    Integrates with EventLog for logging extraction results.
    """

    def __init__(self, eventlog: Optional["EventLog"] = None):
        self.eventlog = eventlog
        self.commit_thresh = COMMITMENT_THRESHOLD

    def extract_best_sentence(self, text: str) -> Optional[str]:
        """
        Extract the best sentence from the text that likely represents a commitment.

        Args:
            text: The input text to analyze.

        Returns:
            The best sentence representing a commitment, or None if no suitable sentence is found.
        """
        if not isinstance(text, str) or not text.strip():
            return None

        # Simple sentence splitting for demonstration; replace with proper NLP sentence tokenization
        sentences = text.split(".")
        sentences = [s.strip() for s in sentences if s.strip()]

        best_sentence = None
        best_score = -1.0

        for sentence in sentences:
            score = self.score(sentence)
            if score > best_score and score >= self.commit_thresh:
                best_score = score
                best_sentence = sentence

        # Log extraction result to EventLog if available
        if self.eventlog:
            self.eventlog.append(
                kind="commitment_extraction",
                content=text,
                meta={
                    "extracted_sentence": best_sentence if best_sentence else "",
                    "score": best_score if best_sentence else 0.0,
                    "threshold": self.commit_thresh,
                },
            )

        return best_sentence

    def score(self, text: str) -> float:
        """
        Score a piece of text based on its likelihood of being a commitment.

        Args:
            text: The text to score.

        Returns:
            A float representing the commitment likelihood score (0.0 to 1.0).
        """
        # Placeholder for scoring logic; replace with actual semantic and structural analysis
        if not text or len(text.split()) < 3:
            return 0.0

        score = 0.5  # Base score for demonstration
        text_lower = text.lower()

        # Boost score for commitment-like keywords
        commitment_keywords = [
            "will",
            "shall",
            "commit",
            "promise",
            "intend",
            "plan",
            "aim",
        ]
        for keyword in commitment_keywords:
            if keyword in text_lower:
                score += 0.1

        # Boost score for first-person pronouns indicating personal commitment
        personal_pronouns = ["i", "we"]
        for pronoun in personal_pronouns:
            if pronoun in text_lower.split():
                score += 0.1

        return min(1.0, max(0.0, score))

    def _vector(self, text: str) -> List[float]:
        """
        Generate a vector representation of the text for semantic analysis.

        Args:
            text: The input text to vectorize.

        Returns:
            A list of floats representing the text vector.
        """
        # Placeholder for vectorization; replace with actual embedding logic
        return [0.0] * 10  # Dummy vector for demonstration
