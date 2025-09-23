"""
LLM-Driven Trait Adjustment System for PMM
Implements a side-layer that allows the LLM to propose and apply personality trait modifications.
This system integrates without touching PMM's foundation code.
"""

from __future__ import annotations
from typing import Dict, List, Any, Optional, Tuple
import re
import os
import logging

logger = logging.getLogger(__name__)


class LLMTraitAdjuster:
    """
    Parses LLM responses for trait adjustment suggestions and validates them against safety bounds.
    Emits standard PMM trait_update events when suggestions pass validation.
    """

    # Regex pattern to detect trait adjustment suggestions in LLM responses
    TRAIT_ADJUSTMENT_PATTERN = re.compile(
        r"(?:suggest|propose|recommend|should|could|might|want to)\s+"
        r"(?:\w+\s+)?"
        r"(increase|decrease|decreasing|adjust|change|modify|raise|lower|boost|reduce|increasing)\s+"
        r"(?:my\s+)?(openness|conscientiousness|extraversion|agreeableness|neuroticism|O|C|E|A|N)\s+"
        r"(?:by\s+|to\s+)?([\+\-]?\d*\.?\d+)",
        re.IGNORECASE,
    )

    def __init__(self, safety_bounds: Optional[Dict] = None):
        """Initialize with configurable safety bounds."""
        self.safety_bounds = safety_bounds or {
            "max_delta_per_adjustment": float(
                os.getenv("PMM_LLM_TRAIT_MAX_DELTA", "0.05")
            ),
            "max_total_daily_change": float(
                os.getenv("PMM_LLM_TRAIT_MAX_DAILY", "0.15")
            ),
            "min_trait_value": 0.0,
            "max_trait_value": 1.0,
            "confidence_threshold": float(
                os.getenv("PMM_LLM_TRAIT_CONFIDENCE_THRESHOLD", "0.6")
            ),
            "max_per_conversation": int(
                os.getenv("PMM_LLM_TRAIT_MAX_PER_CONVERSATION", "1")
            ),
        }

        # Track adjustments for rate limiting
        self.session_adjustments = 0
        self.daily_adjustments = {}  # trait -> total_delta_today

    def parse_trait_suggestions(self, llm_response: str) -> List[Dict[str, Any]]:
        """
        Parse LLM response for trait adjustment suggestions.

        Args:
            llm_response: Raw text from LLM

        Returns:
            List of suggestion dictionaries with keys: trait, delta, confidence, context, source
        """
        suggestions = []

        # Find all matches in the response
        for match in self.TRAIT_ADJUSTMENT_PATTERN.finditer(llm_response):
            try:
                groups = match.groups()
                if len(groups) >= 3:
                    action, trait_name, delta_part = groups[0], groups[1], groups[2]

                    # Normalize trait name
                    trait_code = self._normalize_trait_name(trait_name)
                    if not trait_code:
                        continue

                    # Parse delta value
                    delta = self._parse_delta_value(action, delta_part)
                    if delta is None:
                        continue

                    # Estimate confidence
                    confidence = self._estimate_confidence(match.group(), llm_response)

                    suggestions.append(
                        {
                            "trait": trait_code,
                            "delta": delta,
                            "confidence": confidence,
                            "context": match.group().strip(),
                            "source": "llm_response",
                            "match_position": match.start(),
                        }
                    )

            except (ValueError, IndexError) as e:
                logger.debug(f"Failed to parse trait suggestion: {e}")
                continue

        # Remove duplicate suggestions (keep highest confidence)
        suggestions = self._deduplicate_suggestions(suggestions)

        logger.debug(f"Parsed {len(suggestions)} trait suggestions from LLM response")
        return suggestions

    def _normalize_trait_name(self, trait_name: str) -> Optional[str]:
        """Convert trait names to standard codes."""
        trait_map = {
            "openness": "O",
            "o": "O",
            "O": "O",
            "conscientiousness": "C",
            "c": "C",
            "C": "C",
            "extraversion": "E",
            "e": "E",
            "E": "E",
            "agreeableness": "A",
            "a": "A",
            "A": "A",
            "neuroticism": "N",
            "n": "N",
            "N": "N",
        }
        return trait_map.get(trait_name.lower())

    def _parse_delta_value(self, action: str, delta_part: str) -> Optional[float]:
        """Parse the delta value from the suggestion."""
        try:
            # Extract number from the delta part
            match = re.search(r"[\+\-]?\d*\.?\d+", delta_part)
            if match:
                delta = float(match.group())
                # Apply action direction
                if action.lower() in ["decrease", "decreasing", "reduce", "lower"]:
                    delta = -abs(delta)
                elif action.lower() in ["increase", "increasing", "raise", "boost"]:
                    delta = abs(delta)
                return delta
            else:
                # Default deltas for suggestions without numbers
                if action.lower() in ["increase", "increasing", "raise", "boost"]:
                    return 0.02
                elif action.lower() in ["decrease", "decreasing", "reduce", "lower"]:
                    return -0.02
        except (ValueError, AttributeError):
            pass
        return None

    def _estimate_confidence(self, suggestion_text: str, full_response: str) -> float:
        """Estimate confidence in the LLM's trait suggestion."""
        confidence = 0.5  # Base confidence

        # Higher confidence factors
        if re.search(r"\d", suggestion_text):  # Contains specific numbers
            confidence += 0.2

        if any(
            word in suggestion_text.lower()
            for word in ["should", "recommend", "propose"]
        ):
            confidence += 0.1

        if "because" in suggestion_text.lower() or "since" in suggestion_text.lower():
            confidence += 0.1  # Has reasoning

        # Lower confidence factors
        if len(suggestion_text.split()) < 4:  # Very short suggestion
            confidence -= 0.2

        if any(word in suggestion_text.lower() for word in ["maybe", "might", "could"]):
            confidence -= 0.1  # Hesitant language

        return max(0.0, min(1.0, confidence))

    def _deduplicate_suggestions(self, suggestions: List[Dict]) -> List[Dict]:
        """Remove duplicate suggestions, keeping the highest confidence one."""
        seen = {}
        for suggestion in suggestions:
            trait = suggestion["trait"]
            if (
                trait not in seen
                or suggestion["confidence"] > seen[trait]["confidence"]
            ):
                seen[trait] = suggestion

        return list(seen.values())

    def validate_suggestion(
        self, suggestion: Dict, current_trait_values: Dict
    ) -> Tuple[bool, str]:
        """
        Validate a trait adjustment suggestion against safety bounds.

        Args:
            suggestion: Suggestion dictionary
            current_trait_values: Current trait values (e.g., {'O': 0.8, 'C': 0.5, ...})

        Returns:
            (is_valid, reason)
        """
        trait = suggestion["trait"]
        delta = suggestion["delta"]
        confidence = suggestion["confidence"]

        # Check confidence threshold
        if confidence < self.safety_bounds["confidence_threshold"]:
            return (
                False,
                f"Low confidence ({confidence:.2f} < {self.safety_bounds['confidence_threshold']})",
            )

        # Check delta bounds
        if abs(delta) > self.safety_bounds["max_delta_per_adjustment"]:
            return (
                False,
                f"Delta too large ({abs(delta)} > {self.safety_bounds['max_delta_per_adjustment']})",
            )

        # Check resulting trait value bounds
        current_value = current_trait_values.get(trait, 0.5)
        new_value = current_value + delta

        if new_value < self.safety_bounds["min_trait_value"]:
            return (
                False,
                f"Resulting value too low ({new_value} < {self.safety_bounds['min_trait_value']})",
            )

        if new_value > self.safety_bounds["max_trait_value"]:
            return (
                False,
                f"Resulting value too high ({new_value} > {self.safety_bounds['max_trait_value']})",
            )

        # Check per-conversation limit
        if self.session_adjustments >= self.safety_bounds["max_per_conversation"]:
            return (
                False,
                f"Max adjustments per conversation reached ({self.session_adjustments})",
            )

        # Check daily limits (simplified - would need persistence in real implementation)
        daily_total = sum(self.daily_adjustments.values())
        if daily_total + abs(delta) > self.safety_bounds["max_total_daily_change"]:
            return (
                False,
                f"Daily change limit exceeded ({daily_total + abs(delta)} > {self.safety_bounds['max_total_daily_change']})",
            )

        return True, "Valid"

    def apply_validated_suggestions(
        self, suggestions: List[Dict], current_trait_values: Dict, eventlog
    ) -> List[int]:
        """
        Apply validated trait suggestions and return event IDs.

        Args:
            suggestions: List of validated suggestion dictionaries
            current_trait_values: Current trait values
            eventlog: PMM event log instance

        Returns:
            List of event IDs for applied trait updates
        """
        applied_events = []

        for suggestion in suggestions:
            is_valid, reason = self.validate_suggestion(
                suggestion, current_trait_values
            )
            if not is_valid:
                # Log rejected suggestion
                try:
                    eventlog.append(
                        kind="trait_adjustment_rejected",
                        content="",
                        meta={
                            "suggestion": suggestion,
                            "reason": reason,
                            "source": "llm_trait_adjuster",
                            "safety_bounds": self.safety_bounds,
                        },
                    )
                except Exception as e:
                    logger.warning(f"Failed to log rejected trait suggestion: {e}")
                continue

            # Apply the trait adjustment
            trait = suggestion["trait"]
            delta = suggestion["delta"]

            try:
                event_id = eventlog.append(
                    kind="trait_update",
                    content="",
                    meta={
                        "delta": {trait: delta},
                        "reason": "llm_suggestion",
                        "confidence": suggestion["confidence"],
                        "context": suggestion["context"],
                        "source": "llm_trait_adjuster",
                        "safety_bounds": self.safety_bounds,
                    },
                )

                if event_id:
                    applied_events.append(event_id)
                    self.session_adjustments += 1
                    self.daily_adjustments[trait] = self.daily_adjustments.get(
                        trait, 0
                    ) + abs(delta)

                    logger.info(
                        f"Applied LLM-suggested trait adjustment: {trait} {delta:+.3f} "
                        f"(confidence: {suggestion['confidence']:.2f})"
                    )

            except Exception as e:
                logger.error(f"Failed to apply trait adjustment: {e}")

        return applied_events

    def reset_session_limits(self):
        """Reset per-session adjustment counter."""
        self.session_adjustments = 0

    def reset_daily_limits(self):
        """Reset daily adjustment tracking."""
        self.daily_adjustments.clear()


# Integration function - call this after LLM generates response
def apply_llm_trait_adjustments(
    eventlog, llm_response: str, reset_session: bool = False
) -> List[int]:
    """
    Main integration function to be called after LLM response generation.

    Args:
        eventlog: PMM event log instance
        llm_response: Raw LLM response text
        reset_session: Whether to reset session limits (call at conversation start)

    Returns:
        List of event IDs for applied trait updates
    """
    # Check if LLM trait adjustments are enabled
    if os.getenv("PMM_LLM_TRAIT_ADJUSTMENTS", "").lower() not in ("1", "true", "yes"):
        return []

    try:
        adjuster = LLMTraitAdjuster()

        if reset_session:
            adjuster.reset_session_limits()

        # Parse suggestions from LLM response
        suggestions = adjuster.parse_trait_suggestions(llm_response)

        if not suggestions:
            logger.debug("No trait adjustment suggestions found in LLM response")
            return []

        # Get current trait values
        try:
            from pmm.storage.projection import build_identity

            events = eventlog.read_all()
            identity = build_identity(events)
            current_traits = identity.get("traits", {})
        except Exception as e:
            logger.warning(f"Failed to get current traits: {e}")
            current_traits = {"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5}

        # Apply validated suggestions
        applied_events = adjuster.apply_validated_suggestions(
            suggestions, current_traits, eventlog
        )

        return applied_events

    except Exception as e:
        logger.error(f"LLM trait adjustment failed: {e}")
        return []  # Fail open - don't break main response flow


# Test/example usage
if __name__ == "__main__":
    # Example usage for testing
    adjuster = LLMTraitAdjuster()

    test_responses = [
        "I should increase my openness by 0.03 because this conversation has been very creative.",
        "Maybe I could adjust my conscientiousness a bit.",
        "I recommend decreasing neuroticism by 0.05 to be more stable.",
        "This interaction suggests I should be more agreeable.",
    ]

    for i, response in enumerate(test_responses):
        print(f"\nTest {i+1}: '{response}'")
        suggestions = adjuster.parse_trait_suggestions(response)
        for suggestion in suggestions:
            print(
                f"  → {suggestion['trait']} {suggestion['delta']:+.3f} "
                f"(confidence: {suggestion['confidence']:.2f})"
            )
