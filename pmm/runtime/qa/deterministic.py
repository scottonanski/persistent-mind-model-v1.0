"""Deterministic short-circuit answers for specific user queries."""

from __future__ import annotations

from pmm.runtime.ledger.narrative import get_event_narrative


def _maybe_parse_event_id(text: str) -> int | None:
    """Best-effort event ID extractor using simple token walking (no regex)."""
    if not text:
        return None

    lower = text.lower()
    # Normalize delimiters without introducing regex usage
    normalized = lower.replace("#", " # ")
    for ch in (":", ",", ".", "?", "!", ";", "\n", "\t"):
        normalized = normalized.replace(ch, " ")
    tokens = [token.strip() for token in normalized.split() if token.strip()]

    for idx, token in enumerate(tokens):
        if token != "event":
            continue
        if idx + 1 >= len(tokens):
            continue
        next_token = tokens[idx + 1]
        if next_token == "#":
            if idx + 2 < len(tokens) and tokens[idx + 2].isdigit():
                try:
                    return int(tokens[idx + 2])
                except Exception:
                    return None
        elif next_token.isdigit():
            try:
                return int(next_token)
            except Exception:
                return None
    return None


def try_answer_event_question(ledger, user_text: str) -> str | None:
    """Return deterministic event narrative when the user asks for an event by ID."""
    event_id = _maybe_parse_event_id(user_text or "")
    if event_id is None:
        return None

    narrative = get_event_narrative(ledger, event_id)
    if narrative.confidence == "high":
        marker = ""
    elif narrative.confidence == "medium":
        marker = " [from technical metadata]"
    else:
        marker = " [no narrative data available]"

    return f"Event #{event_id}{marker}: {narrative.text}"
