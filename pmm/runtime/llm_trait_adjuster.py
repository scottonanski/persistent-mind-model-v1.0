"""
LLM-Driven Trait Adjustment System for PMM
Implements a side-layer that allows the LLM to propose and apply personality trait modifications.
This system integrates without touching PMM's foundation code.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class LLMTraitAdjuster:
    """
    Parses LLM responses for trait adjustment suggestions and validates them against safety bounds.
    Emits standard PMM trait_update events when suggestions pass validation.
    """

    # Trait names for deterministic parsing
    TRAIT_NAMES = {
        "openness",
        "conscientiousness",
        "extraversion",
        "agreeableness",
        "neuroticism",
        "o",
        "c",
        "e",
        "a",
        "n",
    }
    ACTION_WORDS = {
        "increase",
        "decrease",
        "decreasing",
        "adjust",
        "change",
        "modify",
        "raise",
        "lower",
        "boost",
        "reduce",
        "increasing",
    }
    SUGGESTION_WORDS = {
        "suggest",
        "propose",
        "recommend",
        "should",
        "could",
        "might",
        "want to",
    }

    def __init__(self, safety_bounds: dict | None = None):
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

        # Feature toggles (default off to preserve existing behavior)
        self.require_citations: bool = str(
            os.getenv("PMM_LLM_TRAIT_REQUIRE_CITATIONS", "0")
        ).lower() in ("1", "true", "yes")
        self.citations_min: int = int(os.getenv("PMM_LLM_TRAIT_CITATIONS_MIN", "2"))
        self.require_cooldown: bool = str(
            os.getenv("PMM_LLM_TRAIT_REQUIRE_COOLDOWN", "0")
        ).lower() in ("1", "true", "yes")
        self.cooldown_reflections_min: int = int(
            os.getenv("PMM_LLM_TRAIT_COOLDOWN_REFLECTIONS_MIN", "3")
        )

        # Track adjustments for rate limiting
        self.session_adjustments = 0
        self.daily_adjustments = {}  # trait -> total_delta_today
        self.session_trait_deltas: dict[str, float] = {}  # per-trait |Δ| this session

    def parse_trait_suggestions(self, llm_response: str) -> list[dict[str, Any]]:
        """
        Parse LLM response for trait adjustment suggestions using deterministic parsing.

        Args:
            llm_response: Raw text from LLM

        Returns:
            List of suggestion dictionaries with keys: trait, delta, confidence, context, source
        """
        suggestions = []
        # Extract any ledger citations present in the full response (e####)
        cited_ids = []
        for word in llm_response.split():
            if word.startswith("e") and len(word) > 2:
                try:
                    num = int(word[1:].rstrip(".,!?;:"))
                    if num >= 10:  # At least 2 digits
                        cited_ids.append(num)
                except ValueError:
                    continue

        # Deterministic parsing: look for patterns in text
        lower_response = llm_response.lower()
        words = lower_response.split()

        # Look for action words and trait names in the word stream
        for i, word in enumerate(words):
            word_clean = word.strip(".,!?;:")
            if word_clean in self.ACTION_WORDS:
                # Check if there's a suggestion word nearby (within 5 words before)
                has_suggestion = False
                for check_idx in range(max(0, i - 5), i):
                    check_word = words[check_idx].strip(".,!?;:")
                    if check_word in self.SUGGESTION_WORDS:
                        has_suggestion = True
                        break

                if not has_suggestion:
                    continue

                # Look for trait name nearby (within 5 words after action)
                for j in range(i + 1, min(len(words), i + 6)):
                    trait_word = words[j].strip(".,!?;:")
                    if trait_word in self.TRAIT_NAMES:
                        # Look for numeric value nearby (within 3 words after trait)
                        for k in range(j + 1, min(len(words), j + 4)):
                            try:
                                delta_str = words[k].strip(".,!?;:+")
                                delta = float(delta_str)

                                # Normalize trait name
                                trait_code = self._normalize_trait_name(trait_word)
                                if not trait_code:
                                    continue

                                # Adjust sign based on action word
                                if word_clean in {
                                    "decrease",
                                    "decreasing",
                                    "lower",
                                    "reduce",
                                }:
                                    delta = -abs(delta)
                                else:
                                    delta = abs(delta)

                                # Extract context (surrounding words)
                                context_start = max(0, i - 5)
                                context_end = min(len(words), k + 5)
                                context = " ".join(words[context_start:context_end])

                                suggestions.append(
                                    {
                                        "trait": trait_code,
                                        "delta": delta,
                                        "confidence": 0.7,
                                        "context": context,
                                        "source": "llm_response",
                                        "match_position": i,
                                        "citations": list(dict.fromkeys(cited_ids))[:4],
                                    }
                                )
                                break
                            except ValueError:
                                continue
                        break  # Found trait, stop looking

        # Remove duplicate suggestions (keep highest confidence)
        suggestions = self._deduplicate_suggestions(suggestions)

        logger.debug(f"Parsed {len(suggestions)} trait suggestions from LLM response")
        return suggestions

    def _normalize_trait_name(self, trait_name: str) -> str | None:
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

    def _parse_delta_value(self, action: str, delta_part: str) -> float | None:
        """Parse the delta value from the suggestion using deterministic parsing."""
        try:
            # Extract number from the delta part deterministically
            delta = None
            for word in delta_part.split():
                word_clean = word.strip("+-.,!?;:")
                try:
                    delta = float(word_clean)
                    break
                except ValueError:
                    continue

            if delta is not None:
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
        if any(c.isdigit() for c in suggestion_text):  # Contains specific numbers
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

    def _deduplicate_suggestions(self, suggestions: list[dict]) -> list[dict]:
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
        self,
        suggestion: dict,
        current_trait_values: dict,
        eventlog: Any | None = None,
    ) -> tuple[bool, str]:
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

        # Optional: require ≥N ledger citations supporting change
        if self.require_citations:
            citations = [
                int(x) for x in (suggestion.get("citations") or []) if str(x).isdigit()
            ]
            if len(citations) < self.citations_min:
                return False, "Insufficient citations: need ≥2 eIDs supporting change"
            if eventlog is None:
                return False, "Ledger unavailable for citations check"
            try:
                events = eventlog.read_all()
            except Exception:
                events = []
            have = {int(ev.get("id") or 0) for ev in events if ev.get("id")}
            valid_cites = [eid for eid in citations if int(eid) in have]
            if len(valid_cites) < self.citations_min:
                return False, "Invalid citations: eIDs not found in ledger"

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

        # Clamp openness nudges near saturation and reject if already maxed
        projected_value = current_value + delta
        if projected_value > self.safety_bounds["max_trait_value"]:
            return (
                False,
                f"Resulting value too high ({projected_value} > {self.safety_bounds['max_trait_value']})",
            )

        if trait == "O" and delta > 0:
            if current_value >= 0.98:
                return (
                    False,
                    "Openness already near saturation; propose a different trait",
                )
            if current_value >= 0.9:
                max_delta = max(0.005, 0.98 - current_value)
                if delta > max_delta:
                    delta = max_delta
                    suggestion["delta"] = delta
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

        # Per-trait session throttle: cumulative |Δ| <= 0.05
        if self.session_trait_deltas.get(trait, 0.0) + abs(delta) > 0.05:
            return False, "Session per-trait delta limit exceeded (|Δ| > 0.05)"

        # Optional: cooldown — require ≥K reflections since last change of same trait
        if self.require_cooldown:
            if eventlog is None:
                return False, "Ledger unavailable for cooldown check"
            try:
                events = eventlog.read_all()
            except Exception:
                events = []
            try:
                last_change_eid: int | None = None
                for ev in reversed(events):
                    if ev.get("kind") != "trait_update":
                        continue
                    meta = ev.get("meta") or {}
                    delta_map = meta.get("delta") or {}
                    if trait in delta_map:
                        last_change_eid = int(ev.get("id") or 0)
                        break
                if last_change_eid is not None:
                    reflections_since = 0
                    for ev in reversed(events):
                        try:
                            eidv = int(ev.get("id") or 0)
                        except Exception:
                            continue
                        if eidv <= int(last_change_eid):
                            break
                        if ev.get("kind") == "reflection":
                            reflections_since += 1
                    if reflections_since < int(self.cooldown_reflections_min):
                        return (
                            False,
                            "Cooldown not satisfied: need more reflections before changing same trait",
                        )
            except Exception:
                return False, "Ledger unavailable for cooldown check"

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
                f"Daily change limit exceeded ({daily_total + abs(delta)} > "
                f"{self.safety_bounds['max_total_daily_change']})",
            )

        return True, "Valid"

    def apply_validated_suggestions(
        self, suggestions: list[dict], current_trait_values: dict, eventlog
    ) -> list[int]:
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
                suggestion, current_trait_values, eventlog
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
                    self.session_trait_deltas[trait] = self.session_trait_deltas.get(
                        trait, 0.0
                    ) + abs(delta)
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
        self.session_trait_deltas.clear()

    def reset_daily_limits(self):
        """Reset daily adjustment tracking."""
        self.daily_adjustments.clear()


# Integration function - call this after LLM generates response
def apply_llm_trait_adjustments(
    eventlog, llm_response: str, reset_session: bool = False
) -> list[int]:
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
    if os.getenv("PMM_LLM_TRAIT_ADJUSTMENTS", "1").lower() not in ("1", "true", "yes"):
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
