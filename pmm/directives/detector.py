from collections.abc import Iterable

from .types import DirectiveCandidate, Source

# ---- Deterministic patterns (module-level constants; no env flags) ----
# Keep this small and transparent. Extend by edits to this table (and tests).
_PATTERN_PREFIXES = (
    "from now on,",
    "always ",
    "never ",
    "directive:",
)


def _normalize_text(text: str) -> str:
    """Trim and collapse internal whitespace deterministically."""
    s = text.strip()
    # Collapse multiple whitespace to single space
    tokens = s.split()
    return " ".join(tokens)


def _extract_body_after_prefix(text: str, prefix: str) -> str | None:
    """
    Extract body text after a prefix, up to first sentence terminator.
    Returns None if prefix not found.
    """
    text_lower = text.lower()
    idx = text_lower.find(prefix.lower())
    if idx == -1:
        return None

    # Check if it's a word boundary (start of text or preceded by non-alnum)
    if idx > 0 and text[idx - 1].isalnum():
        return None

    # Extract text after prefix
    start = idx + len(prefix)
    rest = text[start:].lstrip()

    if not rest:
        return None

    # Find first sentence terminator
    body_chars = []
    for char in rest:
        if char in ".!?\n":
            body_chars.append(char)
            break
        body_chars.append(char)

    return "".join(body_chars).strip()


def extract(
    text: str, source: Source, origin_eid: int | None
) -> Iterable[DirectiveCandidate]:
    """
    Deterministically extract directive candidates from a string.

    - No randomness.
    - De-duplicates within a single call (same content+source).
    - Returns a stable order based on pattern order above.
    """
    norm = _normalize_text(text)
    found: list[DirectiveCandidate] = []

    for prefix in _PATTERN_PREFIXES:
        body = _extract_body_after_prefix(norm, prefix)
        if body:
            body_norm = _normalize_text(body)
            if body_norm:
                found.append(
                    DirectiveCandidate(
                        content=body_norm, source=source, origin_eid=origin_eid
                    )
                )

    # De-dup (content+source) in-order
    seen: set[tuple[str, Source]] = set()
    deduped: list[DirectiveCandidate] = []
    for cand in found:
        key = (cand.content.lower(), cand.source)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cand)

    return deduped
