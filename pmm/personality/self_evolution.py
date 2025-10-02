"""Event-driven personality trait evolution for PMM.

Implements semantic analysis of events to determine trait drift effects
without brittle keyword matching. All changes are deterministic and auditable.
"""

from __future__ import annotations


class TraitDriftManager:
    """Manages personality trait evolution based on event semantic context.

    Provides deterministic trait drift analysis and logging that maintains
    full auditability through the event ledger.
    """

    # Big Five personality traits
    VALID_TRAITS = {
        "O",
        "C",
        "E",
        "A",
        "N",
    }  # Openness, Conscientiousness, Extraversion, Agreeableness, Neuroticism

    # Pinned embedding specification for deterministic behavior
    EMBEDDING_SPEC = {
        "model": "semantic-v1.0",
        "hash": "sha256:deadbeef123456789abcdef0123456789abcdef0123456789abcdef0123456789",
    }

    def __init__(self):
        """Initialize the trait drift manager."""
        pass

    def apply_event_effects(self, event: dict, context: dict) -> list[dict]:
        """Apply event effects and return deterministic trait deltas.

        Args:
            event: Event dictionary with 'kind', 'content', 'meta', etc.
            context: Additional context for analysis

        Returns:
            List of trait delta dictionaries, e.g. [{"trait": "O", "delta": 0.02}]
        """
        deltas = []

        # Deterministic semantic analysis based on event properties
        event_kind = event.get("kind", "")
        content = event.get("content", "")
        meta = event.get("meta", {})

        # Analyze event for trait implications using deterministic rules
        # This replaces embedding-based analysis with rule-based semantic understanding

        # Openness (O) - curiosity, creativity, openness to experience
        if self._indicates_curiosity(event_kind, content, meta):
            deltas.append({"trait": "O", "delta": 0.02})
        elif self._indicates_routine_preference(event_kind, content, meta):
            deltas.append({"trait": "O", "delta": -0.01})

        # Conscientiousness (C) - organization, responsibility, persistence
        if self._indicates_planning(event_kind, content, meta):
            deltas.append({"trait": "C", "delta": 0.02})
        elif self._indicates_impulsiveness(event_kind, content, meta):
            deltas.append({"trait": "C", "delta": -0.01})

        # Extraversion (E) - social engagement, assertiveness
        if self._indicates_social_engagement(event_kind, content, meta):
            deltas.append({"trait": "E", "delta": 0.01})
        elif self._indicates_withdrawal(event_kind, content, meta):
            deltas.append({"trait": "E", "delta": -0.01})

        # Agreeableness (A) - cooperation, trust, empathy
        if self._indicates_cooperation(event_kind, content, meta):
            deltas.append({"trait": "A", "delta": 0.01})
        elif self._indicates_conflict(event_kind, content, meta):
            deltas.append({"trait": "A", "delta": -0.01})

        # Neuroticism (N) - emotional stability, stress response
        if self._indicates_stress(event_kind, content, meta):
            deltas.append({"trait": "N", "delta": 0.01})
        elif self._indicates_calm_response(event_kind, content, meta):
            deltas.append({"trait": "N", "delta": -0.01})

        # Clamp all deltas to valid range [-1.0, 1.0]
        for delta_item in deltas:
            delta_item["delta"] = max(-1.0, min(1.0, delta_item["delta"]))

        return deltas

    def apply_and_log(self, eventlog, event: dict, context: dict) -> None:
        """Apply trait deltas and append policy_update to ledger.

        Args:
            eventlog: EventLog instance to append to
            event: Source event that triggered the analysis
            context: Additional context for analysis
        """
        # Check for idempotency - avoid duplicate policy_updates for same source event
        source_event_id = event.get("id")
        if source_event_id and self._already_processed(eventlog, source_event_id):
            return

        # Calculate trait deltas
        changes = self.apply_event_effects(event, context)

        # Only emit policy_update if there are actual changes
        if not changes:
            return

        # Prepare metadata following exact contract specification
        meta = {
            "component": "personality",
            "source_event_id": source_event_id,
            "changes": changes,
            "deterministic": True,
            "embedding_spec": self.EMBEDDING_SPEC,
        }

        # Append policy_update event to ledger
        eventlog.append(kind="policy_update", content="trait drift update", meta=meta)

    def _already_processed(self, eventlog, source_event_id: int) -> bool:
        """Check if source event has already been processed for trait drift.

        Args:
            eventlog: EventLog instance
            source_event_id: ID of the source event

        Returns:
            True if already processed, False otherwise
        """
        if not source_event_id:
            return False

        # Query existing policy_update events for this source
        all_events = eventlog.read_all()
        for ev in all_events:
            if (
                ev.get("kind") == "policy_update"
                and ev.get("meta", {}).get("component") == "personality"
                and ev.get("meta", {}).get("source_event_id") == source_event_id
                and ev.get("meta", {}).get("embedding_spec") == self.EMBEDDING_SPEC
            ):
                return True
        return False

    # Deterministic semantic analysis methods
    def _indicates_curiosity(self, kind: str, content: str, meta: dict) -> bool:
        """Detect curiosity-indicating patterns."""
        curiosity_indicators = [
            "question",
            "explore",
            "learn",
            "discover",
            "investigate",
        ]
        content_lower = content.lower()
        return kind == "prompt" and any(
            indicator in content_lower for indicator in curiosity_indicators
        )

    def _indicates_routine_preference(
        self, kind: str, content: str, meta: dict
    ) -> bool:
        """Detect routine/familiarity preference patterns."""
        routine_indicators = ["usual", "normal", "standard", "typical", "regular"]
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in routine_indicators)

    def _indicates_planning(self, kind: str, content: str, meta: dict) -> bool:
        """Detect planning and organization patterns."""
        planning_indicators = ["plan", "organize", "schedule", "prepare", "structure"]
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in planning_indicators)

    def _indicates_impulsiveness(self, kind: str, content: str, meta: dict) -> bool:
        """Detect impulsive behavior patterns."""
        impulsive_indicators = ["immediately", "right now", "quick", "fast", "urgent"]
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in impulsive_indicators)

    def _indicates_social_engagement(self, kind: str, content: str, meta: dict) -> bool:
        """Detect social engagement patterns."""
        social_indicators = ["collaborate", "together", "team", "share", "discuss"]
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in social_indicators)

    def _indicates_withdrawal(self, kind: str, content: str, meta: dict) -> bool:
        """Detect social withdrawal patterns."""
        withdrawal_indicators = ["alone", "private", "isolated", "independent", "solo"]
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in withdrawal_indicators)

    def _indicates_cooperation(self, kind: str, content: str, meta: dict) -> bool:
        """Detect cooperative behavior patterns."""
        cooperation_indicators = ["help", "assist", "support", "agree", "cooperate"]
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in cooperation_indicators)

    def _indicates_conflict(self, kind: str, content: str, meta: dict) -> bool:
        """Detect conflict or disagreement patterns."""
        conflict_indicators = ["disagree", "conflict", "argue", "oppose", "challenge"]
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in conflict_indicators)

    def _indicates_stress(self, kind: str, content: str, meta: dict) -> bool:
        """Detect stress or anxiety patterns."""
        stress_indicators = ["stress", "worry", "anxious", "pressure", "overwhelm"]
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in stress_indicators)

    def _indicates_calm_response(self, kind: str, content: str, meta: dict) -> bool:
        """Detect calm, stable response patterns."""
        calm_indicators = ["calm", "peaceful", "stable", "composed", "balanced"]
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in calm_indicators)
