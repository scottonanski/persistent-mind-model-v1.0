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


# All keyword/regex triggers are disabled. No detection from free text.
_PATTERNS: List[re.Pattern] = []


def _normalize(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    s = s.rstrip(" ;,")
    return s


def detect_commitments(
    text: str, *, source: str = "reply"
) -> List[CommitmentCandidate]:
    """Disabled: free-text commitment extraction is not supported.

    Commitments should be opened explicitly via structural events (e.g.,
    reflection_check + commitment_open) and not inferred from keywords.
    """
    return []


class RegexCommitmentDetector:
    """No-op detector. Preserved for API compatibility but returns no results."""

    def find(self, text: str) -> List[Dict]:
        return []


class SemanticCommitmentDetector:
    """No-op stub until semantic detection is implemented structurally."""

    def __init__(self, threshold: float = 0.58):
        self.threshold = threshold

    def find(self, text: str) -> List[Dict]:
        return []


def get_default_detector() -> CommitmentDetector:
    """Return a no-op detector by default."""
    return RegexCommitmentDetector()
