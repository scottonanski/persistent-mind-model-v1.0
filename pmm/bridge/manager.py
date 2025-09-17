"""Bridge manager for prompt/response styling.

Intent:
- Provide a hook for family-aware style handling (e.g., GPT/LLaMA) for a
  consistent voice across chat and reflection.
- Add a deterministic, table-driven sanitizer to remove provider boilerplate
  and identity claims before logging events.
"""

from __future__ import annotations

from typing import List, Dict, Optional
import re


class BridgeManager:
    def __init__(self, model_family: str | None = None) -> None:
        self.model_family = (model_family or "").lower()

    def format_messages(self, messages: List[Dict], *, intent: str) -> List[Dict]:
        """Return a new list of messages, potentially applying style rules."""
        return [dict(m) for m in messages]

    def sanitize(
        self,
        text: str,
        *,
        family: Optional[str] = None,
        adopted_name: Optional[str] = None,
    ) -> str:
        fam = (family or self.model_family) or None
        return sanitize(text, family=fam, adopted_name=adopted_name)


# ---- Deterministic sanitizer (flag-less, table-driven) ----

_WS = re.compile(r"\s+")


def _collapse_ws(s: str) -> str:
    return _WS.sub(" ", (s or "").strip())


def _normalize_ws_preserve_lines(s: str) -> str:
    """Normalize whitespace but preserve line breaks.

    - Trim leading/trailing whitespace
    - Collapse inner runs of spaces/tabs per line
    - Collapse multiple blank lines to a single blank line
    """
    if not s:
        return s
    txt = str(s).strip()
    lines = txt.splitlines()
    norm_lines = [re.sub(r"[ \t]+", " ", ln.strip()) for ln in lines]
    out: list[str] = []
    prev_blank = False
    for ln in norm_lines:
        if ln == "":
            if not prev_blank:
                out.append("")
            prev_blank = True
        else:
            out.append(ln)
            prev_blank = False
    return "\n".join(out).strip()


_STRIP_PREFIXES = (
    # e.g., "As an AI language model, ..." or "As a language model, ..."
    r"^\s*as\s+(?:an?|the)\s+(?:ai\s+language\s+model|language\s+model|ai|assistant)\b[:,]?\s*",
    # e.g., "I am ChatGPT, ..." / "I am a large language model, ..."
    r"^\s*i\s*am\s+(?:chatgpt|an\s+ai|a\s+large\s+language\s+model)\b[:,]?\s*",
)

_STRIP_LINES_CONTAINS = (
    r"^\s*system\s*:\s*.*$",
    r"^\s*assistant\s*:\s*.*$",
    r"^\s*(?:note|disclaimer)\s*:\s*.*$",
    # Common self-awareness disclaimers that harm persona/continuity
    r"^\s*i\s+don'?t\s+(?:have|possess)\s+(?:self[- ]awareness|consciousness|personal\s+experiences|subjective\s+experience)\b.*$",
    r"^\s*i\s+do\s+not\s+(?:have|possess)\s+(?:self[- ]awareness|consciousness|personal\s+experiences|subjective\s+experience)\b.*$",
)

_IDENTITY_PHRASES = (
    r"\bmy\s+name\s+is\s+[^\.\!\?]+[\.\!\?]?",
    r"\bi(?:'|\s*a)m\s+(?:chatgpt|an\s+ai|a\s+large\s+language\s+model)\b[\.\!\?]?",
)


def sanitize(
    text: str,
    *,
    family: Optional[str] = None,
    adopted_name: Optional[str] = None,
) -> str:
    """Deterministically sanitize raw model output.

    - Strip provider boilerplate/preambles/prefixes.
    - Remove mechanical identity claims.
    - Collapse whitespace.
    No randomness. No I/O. No state.
    """
    if not text:
        return text

    s = str(text)

    # 1) Strip known provider prefaces at the start
    for pat in _STRIP_PREFIXES:
        s = re.sub(pat, "", s, flags=re.IGNORECASE)

    # 2) Drop entire lines of role/boilerplate markers
    kept: List[str] = []
    for line in s.splitlines():
        drop = False
        for pat in _STRIP_LINES_CONTAINS:
            if re.search(pat, line, flags=re.IGNORECASE):
                drop = True
                break
        if not drop:
            kept.append(line)
    s = "\n".join(kept)

    # 3) Remove identity-claim phrases anywhere
    for pat in _IDENTITY_PHRASES:
        s = re.sub(pat, "", s, flags=re.IGNORECASE)

    if adopted_name:
        s = re.sub(
            r"\bI\s*(?:am|’m|'m)\s+[A-Za-z0-9_\-]+",
            f"I am {adopted_name}",
            s,
            flags=re.IGNORECASE,
        )

    # 4) Family-specific small trims
    fam = (family or "").lower()
    if fam:
        if "openai" in fam:
            s = re.sub(r"^\s*assistant:\s*", "", s, flags=re.IGNORECASE)
        if ("anthropic" in fam) or ("claude" in fam):
            s = re.sub(r"^\s*helpful\s+assistant[:,]?\s*", "", s, flags=re.IGNORECASE)

    # 5) Whitespace normalization strategy: single-line collapse (no env gate)
    s = _collapse_ws(s)
    return s
