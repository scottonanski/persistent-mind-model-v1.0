import re
from typing import Iterable, List, Tuple
from .types import DirectiveCandidate, Source

# ---- Deterministic patterns (module-level constants; no env flags) ----
# Keep this small and transparent. Extend by edits to this table (and tests).
_PATTERNS: Tuple[re.Pattern, ...] = (
    # "From now on, <do X>" — capture up to first sentence terminator and include it
    re.compile(r"\bfrom now on,\s+(?P<body>[^\.!\?\n]+[\.!\?]?)", re.IGNORECASE),
    # "Always <do X>"
    re.compile(r"\balways\s+(?P<body>[^\.!\?\n]+[\.!\?]?)", re.IGNORECASE),
    # "Never <do X>"
    re.compile(r"\bnever\s+(?P<body>[^\.!\?\n]+[\.!\?]?)", re.IGNORECASE),
    # "Directive: <do X>"
    re.compile(r"\bdirective:\s*(?P<body>[^\.!\?\n]+[\.!\?]?)", re.IGNORECASE),
)


def _normalize_text(text: str) -> str:
    # Trim and collapse internal whitespace deterministically.
    s = text.strip()
    s = re.sub(r"\s+", " ", s)
    return s


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
    found: List[DirectiveCandidate] = []

    for pat in _PATTERNS:
        m = pat.search(norm)
        if not m:
            continue
        body = _normalize_text(m.group("body"))
        if body:
            found.append(
                DirectiveCandidate(content=body, source=source, origin_eid=origin_eid)
            )

    # De-dup (content+source) in-order
    seen: set[tuple[str, Source]] = set()
    deduped: List[DirectiveCandidate] = []
    for cand in found:
        key = (cand.content.lower(), cand.source)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cand)

    return deduped
