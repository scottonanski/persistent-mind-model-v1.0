from __future__ import annotations
from typing import Protocol, List, Dict
import re
from dataclasses import dataclass


class CommitmentDetector(Protocol):
    def find(self, text: str) -> List[Dict]:
        """Return a list of commitments: [{'text': str, 'span': (start, end), 'kind': 'plan'|'followup', 'confidence': float}]"""
        ...


@dataclass(frozen=True)
class CommitmentCandidate:
    text: str
    source: str
    start: int
    end: int


# Table-driven baseline patterns (deterministic order)
_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b(I will|I'll|I shall)\s+([^\.!\n]+)", re.IGNORECASE),
    re.compile(r"\bI can\s+(?:do|handle|set up|create)\s+([^\.!\n]+)", re.IGNORECASE),
    re.compile(r"\bLet's\s+(?!not)\s*([^\.!\n]+)", re.IGNORECASE),
    re.compile(r"\bTODO:\s*([^\n]+)", re.IGNORECASE),
    re.compile(r"\bI commit to\s+([^\.!\n]+)", re.IGNORECASE),
]


def _normalize(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    s = s.rstrip(" ;,")
    return s


def detect_commitments(
    text: str, *, source: str = "reply"
) -> List[CommitmentCandidate]:
    """Deterministic extraction; de-dup by normalized text while preserving pattern order."""
    if not text:
        return []
    out: List[CommitmentCandidate] = []
    seen: set[str] = set()
    for pat in _PATTERNS:
        for m in pat.finditer(text):
            frag = m.group(2) if (m.lastindex and m.lastindex >= 2) else m.group(1)
            norm = _normalize(frag)
            # Canonicalize identity-intent phrases to a stable key
            try:
                m_id = re.search(
                    r"\buse\s+the\s+name\s+([A-Za-z][A-Za-z0-9_-]{0,11})\b",
                    norm,
                    flags=re.IGNORECASE,
                )
                if m_id:
                    nm = m_id.group(1)
                    norm = f"identity:name:{nm}"
            except Exception:
                pass
            if not norm or norm in seen:
                continue
            seen.add(norm)
            out.append(
                CommitmentCandidate(
                    text=norm, source=source, start=m.start(), end=m.end()
                )
            )
    return out


class RegexCommitmentDetector:
    """Brittle but simple baseline; good for smoke. Upgrade path is SemanticCommitmentDetector."""

    def find(self, text: str) -> List[Dict]:
        # Delegate to table-driven baseline to keep a single deterministic source of truth
        cands = detect_commitments(text or "", source="reply")
        results: List[Dict] = []
        for c in cands:
            results.append(
                {
                    "text": c.text,
                    "span": (c.start, c.end),
                    "kind": "plan",
                    "confidence": 0.55,
                }
            )
        return results


class SemanticCommitmentDetector:
    """Stub: swaps in when PMM_DETECTOR=semantic. Implement with embeddings later."""

    def __init__(self, threshold: float = 0.58):
        self.threshold = threshold

    def find(self, text: str) -> List[Dict]:
        # Placeholder: in future, score text against intent exemplars via embeddings similarity.
        # For now, just defer to regex baseline to keep behavior consistent until semantic is wired.
        return RegexCommitmentDetector().find(text)


def get_default_detector() -> CommitmentDetector:
    # Always use deterministic regex baseline; no env gate switching.
    return RegexCommitmentDetector()
