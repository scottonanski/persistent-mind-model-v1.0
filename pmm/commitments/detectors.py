from __future__ import annotations
from typing import Protocol, List, Dict
import os
import re


class CommitmentDetector(Protocol):
    def find(self, text: str) -> List[Dict]:
        """Return a list of commitments: [{'text': str, 'span': (start, end), 'kind': 'plan'|'followup', 'confidence': float}]"""
        ...


_PLAN_RE = re.compile(
    r"\b(?:I|We)\s+(?:will|shall|plan\s+to|intend\s+to|aim\s+to|can|could|should)\b[^.!\n]*",
    flags=re.IGNORECASE,
)
_FOLLOWUP_RE = re.compile(
    r"\b(?:Next|Then|After\s+that|I\s+can\s+next|We\s+can\s+next)\b[^.!\n]*",
    flags=re.IGNORECASE,
)


class RegexCommitmentDetector:
    """Brittle but simple baseline; good for smoke. Upgrade path is SemanticCommitmentDetector."""

    def find(self, text: str) -> List[Dict]:
        results: List[Dict] = []
        for kind, pat in (("plan", _PLAN_RE), ("followup", _FOLLOWUP_RE)):
            for m in pat.finditer(text):
                results.append(
                    {
                        "text": m.group(0).strip(),
                        "span": (m.start(), m.end()),
                        "kind": kind,
                        "confidence": 0.55 if kind == "plan" else 0.50,
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
    if os.getenv("PMM_DETECTOR", "").lower() == "semantic":
        return SemanticCommitmentDetector()
    return RegexCommitmentDetector()
