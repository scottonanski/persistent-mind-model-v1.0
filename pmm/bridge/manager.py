"""Bridge manager for prompt/response styling.

Intent:
- Provide a hook for family-aware style handling (e.g., GPT/LLaMA) for a
  consistent voice across chat and reflection.
- Add a deterministic, table-driven sanitizer to remove provider boilerplate
  and identity claims before logging events.
"""

from __future__ import annotations


class BridgeManager:
    def __init__(self, model_family: str | None = None) -> None:
        self.model_family = (model_family or "").lower()

    def format_messages(self, messages: list[dict], *, intent: str) -> list[dict]:
        """Return a new list of messages, potentially applying style rules."""
        return [dict(m) for m in messages]

    def sanitize(
        self,
        text: str,
        *,
        family: str | None = None,
        adopted_name: str | None = None,
    ) -> str:
        fam = (family or self.model_family) or None
        return sanitize(text, family=fam, adopted_name=adopted_name)


# ---- Deterministic sanitizer (flag-less, table-driven) ----


def _collapse_ws(s: str) -> str:
    from pmm.utils.parsers import normalize_whitespace

    return normalize_whitespace(s or "")


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
    # Normalize spaces/tabs on each line deterministically
    norm_lines = []
    for ln in lines:
        # Replace tabs with spaces and collapse multiple spaces
        cleaned = ln.replace("\t", " ").strip()
        # Collapse multiple spaces
        while "  " in cleaned:
            cleaned = cleaned.replace("  ", " ")
        norm_lines.append(cleaned)
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


# Deterministic string patterns (no regex)
_STRIP_PREFIX_PHRASES = [
    "as an ai language model",
    "as a language model",
    "as an ai",
    "as an assistant",
    "as the assistant",
    "i am chatgpt",
    "i am an ai",
    "i am a large language model",
]

_STRIP_LINE_STARTS = [
    "system:",
    "assistant:",
    "note:",
    "disclaimer:",
    "i don't have self-awareness",
    "i don't have consciousness",
    "i don't possess self-awareness",
    "i don't possess consciousness",
    "i do not have self-awareness",
    "i do not have consciousness",
    "i do not possess self-awareness",
    "i do not possess consciousness",
]

_IDENTITY_REMOVE_PHRASES = [
    "my name is",
    "i'm chatgpt",
    "i am chatgpt",
    "i'm an ai",
    "i am an ai",
    "i'm a large language model",
    "i am a large language model",
]


def sanitize(
    text: str,
    *,
    family: str | None = None,
    adopted_name: str | None = None,
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

    # 1) Strip known provider prefaces at the start (deterministic)
    s_lower = s.lower().lstrip()
    for phrase in _STRIP_PREFIX_PHRASES:
        if s_lower.startswith(phrase):
            # Find where the phrase ends and skip past any punctuation
            rest = s[len(phrase) :]
            # Skip past optional punctuation (: , or space)
            rest = rest.lstrip(":, ")
            s = rest
            s_lower = s.lower().lstrip()
            break

    # 2) Drop entire lines of role/boilerplate markers (deterministic)
    kept: list[str] = []
    for line in s.splitlines():
        line_lower = line.lower().lstrip()
        drop = any(line_lower.startswith(phrase) for phrase in _STRIP_LINE_STARTS)
        if not drop:
            kept.append(line)
    s = "\n".join(kept)

    # 3) Remove identity-claim phrases anywhere (deterministic)
    for phrase in _IDENTITY_REMOVE_PHRASES:
        # Simple case-insensitive removal
        while phrase in s.lower():
            idx = s.lower().find(phrase)
            if idx >= 0:
                # Remove the phrase and any following text until punctuation
                end_idx = idx + len(phrase)
                # Find next sentence terminator
                rest = s[end_idx:]
                term_idx = -1
                for i, char in enumerate(rest):
                    if char in ".!?":
                        term_idx = i + 1
                        break
                if term_idx > 0:
                    s = s[:idx] + rest[term_idx:]
                else:
                    s = s[:idx]
            else:
                break

    if adopted_name:
        name_text = str(adopted_name)
        name_lower = name_text.lower()

        # Deterministic identity swapping: find "I am/I'm <Name>" patterns
        # and replace non-matching names with adopted name
        patterns_to_check = ["i am ", "i'm ", "i'm "]
        for pattern in patterns_to_check:
            idx = 0
            while idx < len(s):
                idx = s.lower().find(pattern, idx)
                if idx < 0:
                    break

                # Check word boundary before "I"
                if idx > 0 and s[idx - 1].isalnum():
                    idx += 1
                    continue

                # Extract candidate name after pattern
                start = idx + len(pattern)
                end = start
                # Find end of name (alphanumeric, dash, underscore, max 16 chars)
                while end < len(s) and end - start < 16:
                    if s[end].isalnum() or s[end] in "_-":
                        end += 1
                    else:
                        break

                if end > start:
                    candidate = s[start:end]
                    # Check if followed by punctuation or end
                    if end < len(s) and s[end] not in " ,.;.;.;.;!?":
                        idx = end
                        continue

                    # If candidate doesn't match adopted name, replace it
                    if candidate.lower() != name_lower and candidate[0].isupper():
                        s = s[:start] + name_text + s[end:]
                        idx = start + len(name_text)
                    else:
                        idx = end
                else:
                    idx += 1

    # 4) Family-specific small trims (deterministic)
    fam = (family or "").lower()
    if fam:
        if "openai" in fam:
            # Remove "assistant:" prefix
            if s.lower().lstrip().startswith("assistant:"):
                s = s.lstrip()[len("assistant:") :].lstrip()
        if ("anthropic" in fam) or ("claude" in fam):
            # Remove "helpful assistant:" prefix
            s_lower = s.lower().lstrip()
            if s_lower.startswith("helpful assistant"):
                rest = s.lstrip()[len("helpful assistant") :]
                if rest and rest[0] in ":,":
                    s = rest[1:].lstrip()
                elif rest:
                    s = rest.lstrip()

    # 5) Whitespace normalization strategy: single-line collapse (no env gate)
    s = _collapse_ws(s)
    return s
