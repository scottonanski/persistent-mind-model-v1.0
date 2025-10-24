"""Natural language generation guards for truth-first output.

Prevents Echo from making false capability claims or fabricating event IDs.
Applied post-generation, pre-emit to ensure factual accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClaimContext:
    """Context for validating capability claims."""

    can_direct_append: bool
    pending_event_id: int | None  # from runtime if available
    next_event_id: int | None  # optional, if runtime exposes it


def guard_capability_claims(text: str, ctx: ClaimContext) -> str:
    """Rewrite capability claims to match actual system behavior.

    Args:
        text: Raw LLM output
        ctx: Runtime context with actual capabilities

    Returns:
        Corrected text with accurate capability claims
    """
    result = text

    # Block direct-creation claims
    if "create" in result.lower() and "event" in result.lower():
        if not ctx.can_direct_append:
            result = result.replace(
                "I can create events",
                "My responses are recorded as events by the runtime",
            )
            result = result.replace(
                "I will create a new event",
                "When I respond, the runtime will append an event",
            )
            result = result.replace(
                "Creating events is a core function",
                "My responses trigger event creation by the runtime",
            )
            result = result.replace(
                "I can generate new events",
                "My responses are recorded as new events by the runtime",
            )

    # Remove speculative event IDs when not confirmed
    if ctx.pending_event_id is None:
        # Strip patterns like 'Event #12345' or 'Event ~12345' when not confirmed
        # Keep historical references (event #333) but remove future speculation
        # Use deterministic token-based parsing instead of regex
        tokens = result.split()
        cleaned_tokens = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            # Check for "Event" followed by "#" or "~" and a 4+ digit number
            if token.lower() == "event" and i + 1 < len(tokens):
                next_token = tokens[i + 1]
                # Check if next token is #12345 or ~12345
                if next_token and next_token[0] in ("#", "~"):
                    num_part = next_token[1:]
                    if num_part.isdigit() and len(num_part) >= 4:
                        # Replace with generic phrase
                        cleaned_tokens.append("a")
                        cleaned_tokens.append("new")
                        cleaned_tokens.append("runtime")
                        cleaned_tokens.append("event")
                        i += 2  # Skip both "Event" and "#12345"
                        continue
            cleaned_tokens.append(token)
            i += 1
        result = " ".join(cleaned_tokens)

    return result
