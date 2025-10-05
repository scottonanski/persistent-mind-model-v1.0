"""Prompt constraint helpers (Stage 4 extraction).

Extracts constraint detection and voice sanitation functions from monolithic loop.py.
All behavior preserved exactly as-is per CONTRIBUTING.md.
"""

from __future__ import annotations

from pmm.utils.parsers import tokenize_alphanumeric


def count_words(s: str) -> int:
    """Count words in text using deterministic tokenization."""
    return len(tokenize_alphanumeric(s or ""))


def wants_exact_words(cmd: str) -> int | None:
    """Extract exact word count constraint from command."""
    if not cmd:
        return None

    try:
        tokens = cmd.lower().split()
        for i, token in enumerate(tokens):
            if token == "exactly" and i + 2 < len(tokens):
                # Look for "exactly <number> word(s)"
                if tokens[i + 2].startswith("word"):
                    try:
                        return int(tokens[i + 1])
                    except ValueError:
                        continue
    except Exception:
        return None
    return None


def wants_no_commas(cmd: str) -> bool:
    """Check if command requests no commas."""
    if not cmd:
        return False
    return "no commas" in cmd.lower() or "no comma" in cmd.lower()


def wants_bullets(cmd: str, labels: tuple[str, str] = ("One:", "Two:")) -> bool:
    """Check if command requests bullet-style output."""
    low = (cmd or "").lower()
    # Heuristic: look for fork-style instruction requiring two bullets
    return ("two" in low and "five words" in low) or (
        "bullets" in low and all(lbl in low for lbl in ["one", "two"])
    )


def forbids_preamble(cmd: str, name: str) -> bool:
    """Check if command forbids identity preambles.

    For short-form constrained outputs, avoid persona prefaces.
    """
    low = (cmd or "").lower()
    if any(
        k in low
        for k in (
            "exactly",
            "no commas",
            "five words",
            'reply "yes" or "no"',
        )
    ):
        return True
    # Also if explicitly asked not to add prefaces/signatures
    return ("do not add" in low or "do not include" in low) and (
        "preface" in low or "signature" in low or "name" in low
    )


def strip_voice_wrappers(text: str, name: str) -> str:
    """Strip identity preambles from text."""
    if not text or not name:
        return text

    text = text.strip()
    name_lower = name.lower()
    text_lower = text.lower()

    # Check for "I am <name>" or "I'm <name>" at start
    prefixes = [
        f"i am {name_lower}",
        f"i'm {name_lower}",
        f"i'm {name_lower}",
        f"my name is {name_lower}",
    ]

    for prefix in prefixes:
        if text_lower.startswith(prefix):
            # Remove the prefix, handling optional punctuation
            rest = text[len(prefix) :].lstrip()
            if rest and rest[0] in ".!":
                rest = rest[1:].lstrip()
            return rest

    return text


__all__ = [
    "count_words",
    "wants_exact_words",
    "wants_no_commas",
    "wants_bullets",
    "forbids_preamble",
    "strip_voice_wrappers",
]
