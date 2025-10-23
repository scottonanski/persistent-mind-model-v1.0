from __future__ import annotations


def normalize_key(name: str) -> str:
    """Normalize a trait key to lowercase for consistency across the stack.

    All emitters/readers MUST call this before using trait keys.
    """
    return (name or "").strip().lower()


# Default trait values for initialization
DEFAULT_TRAITS = {
    "openness": 0.5,
    "conscientiousness": 0.5,
    "extraversion": 0.5,
    "agreeableness": 0.5,
    "neuroticism": 0.5,
}
