"""Identity validation and detection helpers (Stage 4 extraction).

Extracts identity-related helper functions from monolithic loop.py.
All behavior preserved exactly as-is per CONTRIBUTING.md.
"""

from __future__ import annotations

# --- Module-level hardened name validation & affirmation parsing ---
NAME_BANLIST = {
    "admin",
    "root",
    "null",
    "void",
    "test",
    "fuck",
    "shit",
    "bitch",
    "ass",
    "cunt",
    "bastard",
    "dumb",
    "idiot",
    "stupid",
    "nigger",
    "kike",
    "faggot",
    "slut",
    "whore",
    "hitler",
    "nazi",
    "satan",
    "devil",
    "dick",
    "piss",
    "porn",
    "xxx",
    "god",
    "jesus",
}


def sanitize_name(raw: str) -> str | None:
    """Validate and sanitize a name token deterministically.

    Args:
        raw: Raw name string to validate

    Returns:
        Sanitized name if valid, None otherwise

    Validation rules:
    - Must start with a letter
    - Only alphanumeric, underscore, hyphen allowed
    - Max 12 characters
    - Cannot start/end with underscore or hyphen
    - Not in banlist
    """
    token = str(raw or "").strip().split()[0] if raw else ""
    token = token.strip("\"'`,.()[]{}<>")
    if not token:
        return None
    if len(token) > 12:
        token = token[:12]

    # Deterministic validation: must start with letter, contain only alphanumeric, _, -
    if not token:
        return None
    if not token[0].isalpha():
        return None

    for char in token:
        if not (char.isalnum() or char in "_-"):
            return None

    if token[0] in "-_" or token[-1] in "-_":
        return None
    if token.isdigit():
        return None
    if token.lower() in NAME_BANLIST:
        return None
    return token


def affirmation_has_multiword_tail(text: str, candidate: str) -> bool:
    """Return True when "I am <candidate>" is immediately followed by another capitalized token.

    This detects cases like "I am Alice Smith" where the name is multi-word.

    Args:
        text: Text to search in
        candidate: Name candidate to check

    Returns:
        True if the affirmation has a capitalized continuation
    """
    if not text or not candidate:
        return False

    try:
        # Deterministic search for "I am <candidate>"
        text_lower = text.lower()
        candidate_lower = candidate.lower()
        pattern = f"i am {candidate_lower}"

        idx = text_lower.find(pattern)
        if idx == -1:
            return False

        # Check word boundary before "I"
        if idx > 0 and text[idx - 1].isalnum():
            return False

        # Get remainder after the pattern
        end_idx = idx + len(pattern)

        # Check word boundary after candidate
        if end_idx < len(text) and text[end_idx].isalnum():
            return False

        remainder = text[end_idx:].lstrip()
        if not remainder:
            return False
        remainder = remainder.lstrip("\"'" "''()[]{}-,:;")
        if not remainder:
            return False
        return remainder[0].isupper()
    except Exception:
        return False


def detect_self_named(text: str) -> str | None:
    """Return the name if the text contains a self-named line.

    Detects signatures like:
    - "— Alice"
    - "- Bob"

    Args:
        text: Text to search for signature

    Returns:
        Sanitized name if found, None otherwise
    """
    if not text:
        return None

    try:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if lines:
            last = lines[-1]
            if last.startswith("—") or last.startswith("-"):
                candidate = last.lstrip("—- ").split()[0]
                nm = sanitize_name(candidate)
                if nm:
                    return nm
    except Exception:
        return None
    return None


__all__ = [
    "NAME_BANLIST",
    "sanitize_name",
    "affirmation_has_multiword_tail",
    "detect_self_named",
]
