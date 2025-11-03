"""
Hypothesis lifecycle management for Phase 3 proactive synthesis.

Tracks hypotheses from creation through validation, with deterministic
state transitions and full audit trails.

Hypothesis format: "If <condition> then <measurable effect> within <window> measured by <metric>"
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from pmm.runtime.scoring import HypothesisScore, get_scorer
from pmm.storage.eventlog import EventLog


class HypothesisStatus(Enum):
    """Deterministic hypothesis states."""

    ACTIVE = "active"
    SUPPORTED = "supported"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


@dataclass
class Hypothesis:
    """Immutable hypothesis core with mutable state."""

    id: int
    statement: str  # "If X then Y within Z measured by M"
    condition: str  # X part of the statement
    prediction: str  # Y part of the statement
    window: str  # Z part (time or event window)
    metric: str  # M part (measurement metric)
    priors: float  # Prior probability (0-1)
    evidence_tokens: list[str]  # [id:digest] citations
    status: HypothesisStatus
    created_at: str
    updated_at: str
    posterior: float  # Updated probability after evidence
    confidence: float  # Confidence in posterior
    supporting_evidence: int  # Count of supporting observations
    contradicting_evidence: int  # Count of contradicting observations


class HypothesisTracker:
    """
    Tracks hypothesis lifecycle with deterministic state transitions.

    All state changes are logged to the eventlog for full auditability.
    """

    def __init__(self, eventlog: EventLog):
        self.eventlog = eventlog
        self.scorer = get_scorer()
        self._active_hypotheses: dict[int, Hypothesis] = {}
        self._max_concurrent = 3  # Safety limit
        self._min_confidence_threshold = 0.7  # Minimum for status changes

    def parse_hypothesis_statement(
        self, statement: str
    ) -> tuple[str, str, str, str] | None:
        """Parse hypothesis statement into components using deterministic parsing.

        Expected format: "If <condition> then <prediction> within <window> measured by <metric>"

        Returns:
            Tuple of (condition, prediction, window, metric) or None if format is invalid.
        """
        if not statement:
            return None

        stmt = statement.strip()

        # Check if statement starts with "If"
        if not stmt.lower().startswith("if "):
            return None

        # Find "then" keyword
        then_idx = stmt.lower().find(" then ")
        if then_idx == -1:
            return None

        # Find "within" keyword
        within_idx = stmt.lower().find(" within ")
        if within_idx == -1:
            return None

        # Find "measured by" keyword
        measured_idx = stmt.lower().find(" measured by ")
        if measured_idx == -1:
            return None

        # Extract components
        condition = stmt[3:then_idx].strip()  # Remove "If "
        prediction = stmt[then_idx + 6 : within_idx].strip()  # Remove " then "
        window = stmt[within_idx + 8 : measured_idx].strip()  # Remove " within "
        metric = stmt[measured_idx + 13 :].strip()  # Remove " measured by "

        if not all([condition, prediction, window, metric]):
            return None

        return condition, prediction, window, metric

    def validate_evidence_tokens(self, tokens: list[str]) -> list[str]:
        """
        Validate evidence tokens are in correct [id:digest] format.

        Args:
            tokens: List of token strings to validate

        Returns:
            List of valid tokens (invalid ones filtered out)
        """
        valid_tokens = []

        for token in tokens:
            token_clean = token.strip()

            # Check [id:digest] format deterministically
            if not (token_clean.startswith("[") and token_clean.endswith("]")):
                continue

            inner = token_clean[1:-1]  # Remove brackets

            if ":" not in inner:
                continue

            parts = inner.split(":", 1)
            if len(parts) != 2:
                continue

            # Check if first part is an integer (event ID)
            try:
                event_id = int(parts[0])
            except ValueError:
                continue

            # Check if second part is hex (digest) - lowercase only
            digest = parts[1]
            if not digest or not all(c in "0123456789abcdef" for c in digest):
                continue

            # Verify the event actually exists
            try:
                event = self.eventlog.get_event(event_id)
                if event:
                    valid_tokens.append(token_clean)
            except Exception:
                continue

        return valid_tokens

    def create_hypothesis(
        self,
        statement: str,
        priors: float = 0.5,
        evidence_tokens: list[str] | None = None,
    ) -> Hypothesis | None:
        """
        Create a new hypothesis with validation.

        Args:
            statement: Hypothesis statement in required format
            priors: Prior probability (0-1)
            evidence_tokens: List of evidence citations

        Returns:
            Created hypothesis or None if validation fails
        """
        # Check concurrent hypothesis limit
        if len(self._active_hypotheses) >= self._max_concurrent:
            return None

        # Parse statement
        parsed = self.parse_hypothesis_statement(statement)
        if not parsed:
            return None

        condition, prediction, window, metric = parsed

        # Validate priors
        if not (0.0 <= priors <= 1.0):
            return None

        # Validate evidence tokens
        valid_tokens = self.validate_evidence_tokens(evidence_tokens or [])
        if len(valid_tokens) < 1:  # Require at least one evidence token
            return None

        # Create hypothesis
        timestamp = datetime.utcnow().isoformat() + "Z"
        hypothesis_id = self.eventlog.append(
            kind="hypothesis_open",
            content=statement,
            meta={
                "condition": condition,
                "prediction": prediction,
                "window": window,
                "metric": metric,
                "priors": priors,
                "evidence_tokens": valid_tokens,
                "status": HypothesisStatus.ACTIVE.value,
                "posterior": priors,
                "confidence": 0.5,  # Initial confidence
                "supporting_evidence": 0,
                "contradicting_evidence": 0,
            },
        )

        hypothesis = Hypothesis(
            id=hypothesis_id,
            statement=statement,
            condition=condition,
            prediction=prediction,
            window=window,
            metric=metric,
            priors=priors,
            evidence_tokens=valid_tokens,
            status=HypothesisStatus.ACTIVE,
            created_at=timestamp,
            updated_at=timestamp,
            posterior=priors,
            confidence=0.5,
            supporting_evidence=0,
            contradicting_evidence=0,
        )

        self._active_hypotheses[hypothesis_id] = hypothesis

        return hypothesis

    def add_evidence(
        self,
        hypothesis_id: int,
        outcome: bool,  # True for supporting, False for contradicting
        metric_value: float | None = None,
        evidence_tokens: list[str] | None = None,
    ) -> bool:
        """
        Add evidence to hypothesis and update posterior.

        Args:
            hypothesis_id: ID of hypothesis to update
            outcome: Whether evidence supports (True) or contradicts (False)
            metric_value: Measured metric value if applicable
            evidence_tokens: Additional evidence citations

        Returns:
            True if evidence was added, False otherwise
        """
        if hypothesis_id not in self._active_hypotheses:
            return False

        hypothesis = self._active_hypotheses[hypothesis_id]

        # Validate additional evidence tokens
        valid_tokens = self.validate_evidence_tokens(evidence_tokens or [])

        # Update evidence counts
        if outcome:
            hypothesis.supporting_evidence += 1
        else:
            hypothesis.contradicting_evidence += 1

        # Calculate new posterior using Bayesian updating
        total_evidence = (
            hypothesis.supporting_evidence + hypothesis.contradicting_evidence
        )

        if total_evidence > 0:
            # Beta distribution update (deterministic)
            alpha = hypothesis.priors * 10  # Prior strength
            beta = (1 - hypothesis.priors) * 10

            posterior_alpha = alpha + hypothesis.supporting_evidence
            posterior_beta = beta + hypothesis.contradicting_evidence

            hypothesis.posterior = posterior_alpha / (posterior_alpha + posterior_beta)

            # Update confidence based on evidence volume
            hypothesis.confidence = min(1.0, total_evidence / 10.0)

        hypothesis.updated_at = datetime.utcnow().isoformat() + "Z"

        # Log evidence addition
        self.eventlog.append(
            kind="hypothesis_evidence",
            content=f"Added evidence to hypothesis {hypothesis_id}: {'support' if outcome else 'contradiction'}",
            meta={
                "hypothesis_id": hypothesis_id,
                "outcome": outcome,
                "metric_value": metric_value,
                "evidence_tokens": valid_tokens,
                "posterior": hypothesis.posterior,
                "confidence": hypothesis.confidence,
                "supporting_evidence": hypothesis.supporting_evidence,
                "contradicting_evidence": hypothesis.contradicting_evidence,
            },
        )

        # Check for status transition
        self._maybe_update_status(hypothesis_id)

        return True

    def _maybe_update_status(self, hypothesis_id: int) -> None:
        """
        Update hypothesis status based on evidence and confidence.

        Uses deterministic thresholds for state transitions.
        """
        if hypothesis_id not in self._active_hypotheses:
            return

        hypothesis = self._active_hypotheses[hypothesis_id]
        old_status = hypothesis.status

        # Deterministic status transition rules
        if hypothesis.confidence >= self._min_confidence_threshold:
            if hypothesis.posterior >= 0.8:
                hypothesis.status = HypothesisStatus.SUPPORTED
            elif hypothesis.posterior <= 0.2:
                hypothesis.status = HypothesisStatus.REJECTED
            else:
                hypothesis.status = HypothesisStatus.INCONCLUSIVE
        else:
            # Keep active if confidence is low
            hypothesis.status = HypothesisStatus.ACTIVE

        # Log status change if it happened
        if old_status != hypothesis.status:
            self.eventlog.append(
                kind="hypothesis_update",
                content=f"Hypothesis {hypothesis_id} status: {old_status.value} → {hypothesis.status.value}",
                meta={
                    "id": hypothesis_id,
                    "posterior": hypothesis.posterior,
                    "status": hypothesis.status.value,
                },
            )

    def get_active_hypotheses(self) -> list[Hypothesis]:
        """Get all currently active hypotheses."""
        return [
            h
            for h in self._active_hypotheses.values()
            if h.status == HypothesisStatus.ACTIVE
        ]

    def get_supported_hypotheses(self) -> list[Hypothesis]:
        """Get all supported hypotheses ready for belief updates."""
        return [
            h
            for h in self._active_hypotheses.values()
            if h.status == HypothesisStatus.SUPPORTED
        ]

    def get_hypothesis(self, hypothesis_id: int) -> Hypothesis | None:
        """Get hypothesis by ID."""
        return self._active_hypotheses.get(hypothesis_id)

    def close_hypothesis(self, hypothesis_id: int) -> bool:
        """
        Close hypothesis and remove from active tracking.

        Args:
            hypothesis_id: ID of hypothesis to close

        Returns:
            True if hypothesis was closed, False otherwise
        """
        if hypothesis_id not in self._active_hypotheses:
            return False

        hypothesis = self._active_hypotheses[hypothesis_id]

        # Log closure
        self.eventlog.append(
            kind="hypothesis_close",
            content=f"Closed hypothesis {hypothesis_id} with status {hypothesis.status.value}",
            meta={
                "id": hypothesis_id,
                "final_status": hypothesis.status.value,
                "final_posterior": hypothesis.posterior,
                "final_confidence": hypothesis.confidence,
            },
        )

        # Remove from active tracking
        del self._active_hypotheses[hypothesis_id]

        return True

    def get_hypothesis_score(self, hypothesis_id: int) -> HypothesisScore | None:
        """
        Get scoring metrics for hypothesis.

        Args:
            hypothesis_id: ID of hypothesis to score

        Returns:
            HypothesisScore or None if hypothesis not found
        """
        hypothesis = self.get_hypothesis(hypothesis_id)
        if not hypothesis:
            return None

        # Convert evidence counts to scoring metrics
        true_positives = hypothesis.supporting_evidence
        false_positives = max(0, hypothesis.contradicting_evidence // 2)  # Estimate
        true_negatives = max(0, hypothesis.contradicting_evidence // 2)  # Estimate
        false_negatives = hypothesis.contradicting_evidence

        return self.scorer.score_hypothesis(
            true_positives=true_positives,
            false_positives=false_positives,
            true_negatives=true_negatives,
            false_negatives=false_negatives,
            baseline_performance=hypothesis.priors,
        )

    def cleanup_expired_hypotheses(self, max_age_hours: int = 24) -> int:
        """
        Clean up old inactive hypotheses to prevent memory bloat.

        Args:
            max_age_hours: Maximum age for inactive hypotheses

        Returns:
            Number of hypotheses cleaned up
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        cleanup_count = 0

        for hypothesis_id, hypothesis in list(self._active_hypotheses.items()):
            # Skip active hypotheses
            if hypothesis.status == HypothesisStatus.ACTIVE:
                continue

            # Parse timestamp
            try:
                # Handle both Z suffix and timezone offset formats
                if hypothesis.updated_at.endswith("Z"):
                    updated_time = datetime.fromisoformat(
                        hypothesis.updated_at.replace("Z", "+00:00")
                    )
                else:
                    updated_time = datetime.fromisoformat(hypothesis.updated_at)

                if updated_time < cutoff_time:
                    self.close_hypothesis(hypothesis_id)
                    cleanup_count += 1
            except (ValueError, AttributeError):
                # Close if timestamp is invalid
                self.close_hypothesis(hypothesis_id)
                cleanup_count += 1

        return cleanup_count
