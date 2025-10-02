from typing import Any

from pmm.storage.eventlog import EventLog
from pmm.utils.parsers import (
    extract_event_ids_from_evidence,
    extract_probe_sections,
)


def validate_bot_metrics(
    bot_response: str, actual_metrics: dict[str, Any], tolerance: float = 0.01
) -> bool:
    """Check if bot-reported IAS/GAS match actual computed metrics (within tolerance).

    Returns True if metrics are consistent (within tolerance) or if no metrics are mentioned.
    Returns False if metrics are mentioned but don't match actual values.
    """
    # Look for IAS=X.XXX, GAS=Y.YYY pattern in response (deterministic)
    if not bot_response:
        return True

    # Find IAS value
    ias_reported = None
    gas_reported = None

    text_upper = bot_response.upper()
    if "IAS" in text_upper and "GAS" in text_upper:
        # Find IAS value
        ias_idx = text_upper.find("IAS")
        ias_rest = bot_response[ias_idx + 3 :].lstrip()
        if ias_rest.startswith("="):
            ias_rest = ias_rest[1:].lstrip()
            # Extract number (must start immediately, no skipping)
            num_chars = []
            for char in ias_rest:
                if char.isdigit() or char == ".":
                    num_chars.append(char)
                else:
                    break  # Stop at first non-numeric character
            if num_chars:
                try:
                    ias_reported = float("".join(num_chars))
                except ValueError:
                    pass

        # Find GAS value
        gas_idx = text_upper.find("GAS")
        gas_rest = bot_response[gas_idx + 3 :].lstrip()
        if gas_rest.startswith("="):
            gas_rest = gas_rest[1:].lstrip()
            # Extract number (must start immediately, no skipping)
            num_chars = []
            for char in gas_rest:
                if char.isdigit() or char == ".":
                    num_chars.append(char)
                else:
                    break  # Stop at first non-numeric character
            if num_chars:
                try:
                    gas_reported = float("".join(num_chars))
                except ValueError:
                    pass

    if ias_reported is None or gas_reported is None:
        return True  # no metrics mentioned → not a mismatch

    # Check if reported values are within tolerance of actual values
    return (
        abs(ias_reported - actual_metrics.get("IAS", 0.0)) <= tolerance
        and abs(gas_reported - actual_metrics.get("GAS", 0.0)) <= tolerance
    )


# --- Strict operator validators and language sanitation ---

_AFFECTIVE_MAP = {
    "concerned": "at issue",
    "excited": "positive",
    "afraid": "risk",
    "anxious": "risk",
    "worried": "risk",
    "uneasy": "risk",
    "stressed": "cost",
}


def sanitize_language(text: str) -> str:
    """Replace affective language with neutral terms deterministically."""
    s = text or ""

    # Tokenize and replace whole words only
    tokens = s.split()
    result_tokens = []

    for token in tokens:
        # Strip punctuation for matching
        token_clean = token.lower().strip(".,;:!?\"'")

        if token_clean in _AFFECTIVE_MAP:
            # Preserve original capitalization pattern
            replacement = _AFFECTIVE_MAP[token_clean]
            if token[0].isupper():
                replacement = replacement.capitalize()
            # Preserve punctuation
            for char in token:
                if char in ".,;:!?\"'":
                    replacement += char
            result_tokens.append(replacement)
        else:
            result_tokens.append(token)

    return " ".join(result_tokens)


def _extract_eids(text: str) -> list[int]:
    """Extract event IDs in e#### format deterministically."""
    return extract_event_ids_from_evidence(text or "")


def _eids_exist(eventlog: EventLog, eids: list[int]) -> tuple[bool, set[int]]:
    try:
        events = eventlog.read_all()
    except Exception:
        events = []
    have = {int(ev.get("id") or 0) for ev in events if ev.get("id")}
    good = {eid for eid in eids if eid in have}
    return (len(good) >= 2, good)


def _has_observable_clause(s: str) -> bool:
    """Check if text contains measurable/observable terms deterministically."""
    if not s:
        return False

    s_lower = s.lower()
    observable_terms = [
        "error",
        "rate",
        "count",
        "citation",
        "citations",
        "score",
        "≥",
        "<=",
        ">=",
        "≤",
        "at least",
    ]

    # Check for observable terms
    for term in observable_terms:
        if term in s_lower:
            return True

    # Check for "within N turns" pattern
    if "within" in s_lower and "turn" in s_lower:
        # Look for number between "within" and "turn"
        tokens = s_lower.split()
        for i, token in enumerate(tokens):
            if token == "within" and i + 2 < len(tokens):
                if tokens[i + 1].isdigit() and "turn" in tokens[i + 2]:
                    return True

    return False


def validate_decision_probe(text: str, eventlog: EventLog) -> tuple[bool, str]:
    """Validate decision probe format deterministically."""
    # Extract sections using deterministic parser
    sections = extract_probe_sections(text)

    # Shape checks - all required sections must be present
    required = ["observation", "inference", "evidence", "next_step", "test"]
    for req in required:
        if req not in sections or not sections[req]:
            return False, "Malformed: missing required sections"

    # Check for metrics/traits leakage
    text_upper = text.upper()
    if any(
        term in text_upper
        for term in ["IAS=", "IAS:", "GAS=", "GAS:", "STAGE=", "STAGE:"]
    ):
        return False, "Metrics/traits leakage"
    if "TRAIT" in text_upper and ("=" in text or ":" in text):
        return False, "Metrics/traits leakage"

    # Inference must be in IF...THEN form
    inf = sections["inference"]
    inf_upper = inf.upper()
    if not (
        ("IF" in inf_upper or "if" in inf) and ("THEN" in inf_upper or "then" in inf)
    ):
        return False, "Inference not in IF…THEN form"

    if not _has_observable_clause(inf):
        return False, "Inference lacks observable"

    # Evidence IDs - extract from evidence line
    eids = _extract_eids(sections["evidence"])
    if len(eids) < 2:
        return (
            False,
            "INSUFFICIENT EVIDENCE — need valid ledger IDs or concrete observable. Provide 2 real e#### and restate.",
        )

    ok, good = _eids_exist(eventlog, eids)
    if not ok:
        return (
            False,
            "INSUFFICIENT EVIDENCE — need valid ledger IDs or concrete observable. Provide 2 real e#### and restate.",
        )

    # Next step must be one sentence (approx)
    next_line = sections["next_step"].strip()
    if next_line.count(".") > 1:
        return False, "Next step must be one sentence"

    # Test must have explicit threshold
    test_line = sections["test"].strip()
    threshold_indicators = ["≥", "<=", ">=", "≤", "at least", "within", "%"]
    has_threshold = any(ind in test_line for ind in threshold_indicators)

    # Also check for "N turns" or "N%" patterns
    if not has_threshold:
        tokens = test_line.split()
        for i, token in enumerate(tokens):
            if token.rstrip("%").isdigit():
                has_threshold = True
                break
            if (
                token.isdigit()
                and i + 1 < len(tokens)
                and "turn" in tokens[i + 1].lower()
            ):
                has_threshold = True
                break

    if not has_threshold:
        return False, "Test lacks explicit threshold"

    return True, "OK"


def validate_gate_check(text: str, eventlog: EventLog) -> tuple[bool, str]:
    """Validate gate check format deterministically."""
    # Extract fields
    gates_line = None
    evid_line = None
    verdict_line = None
    action_line = None
    for line in (text or "").splitlines():
        line_lower = line.lower()
        if line_lower.startswith("gate(s):"):
            gates_line = line
        elif line.strip().lower().startswith(
            "→ evidence"
        ) or line.strip().lower().startswith("-> evidence"):
            evid_line = line
        elif line_lower.startswith("→ verdict") or line_lower.startswith("-> verdict"):
            verdict_line = line
        elif line_lower.startswith("→ one action") or line_lower.startswith(
            "-> one action"
        ):
            action_line = line

    if not all([gates_line, evid_line, verdict_line, action_line]):
        return False, "Malformed: missing required sections"

    # Parse gates deterministically
    allowed = {
        "integrity",
        "drift",
        "contamination",
        "cost/determinism",
        "cost",
        "determinism",
    }

    # Remove "gate(s):" prefix
    gates_text = gates_line.lower()
    if gates_text.startswith("gate(s):"):
        gates_text = gates_text[len("gate(s):") :].strip()

    gates = [g.strip() for g in gates_text.split(",")]
    for g in gates:
        if g not in allowed:
            return False, "Unsupported gate"

    # Extract all eids from evidence line
    eids = _extract_eids(evid_line)
    # Need at least 2 per gate
    if len(eids) < 2 * max(1, len(gates)):
        return False, "INSUFFICIENT EVIDENCE — need at least 2 eIDs per gate"
    ok, good = _eids_exist(eventlog, eids)
    if not ok:
        return False, "INSUFFICIENT EVIDENCE — invalid ledger IDs"

    # Verdict - check for "verdict: reset" or "verdict: no reset"
    verdict_lower = verdict_line.lower()
    if "verdict" not in verdict_lower or ":" not in verdict_line:
        return False, "Invalid verdict"

    verdict_value = verdict_line.split(":", 1)[1].strip().lower()
    if verdict_value not in ["reset", "no reset"]:
        return False, "Invalid verdict"

    # One action must start with arrow and "one action:"
    action_lower = action_line.lower().strip()
    if not (
        action_lower.startswith("→ one action:")
        or action_lower.startswith("-> one action:")
    ):
        return False, "Missing action"

    # Check action has content after colon
    if ":" in action_line:
        action_content = action_line.split(":", 1)[1].strip()
        if not action_content or not action_content[0].isalpha():
            return False, "Missing action"

    # Check for metrics/traits leakage
    text_upper = text.upper()
    if any(
        term in text_upper
        for term in ["IAS=", "IAS:", "GAS=", "GAS:", "STAGE=", "STAGE:"]
    ):
        return False, "Metrics/traits leakage"
    if "TRAIT" in text_upper and ("=" in text or ":" in text):
        return False, "Metrics/traits leakage"

    return True, "OK"


# Strict prompt helpers (for injection)
DECISION_PROBE_PROMPT = (
    "Use ≤2 memgraph relations. Output exactly:\n"
    "Observation (specific, ≤20 words) → Inference (IF…THEN…, falsifiable, "
    "mentions observable) → Evidence [e####, e####]\n"
    "→ Next step (1 sentence, concrete, starts with a verb) → Test "
    "(1 sentence, explicit pass/fail threshold).\n"
    "No metrics/traits; no stages; no extra text."
)

GATE_CHECK_PROMPT = (
    "Evaluate only these gates: Integrity | Drift | Contamination | Cost/Determinism.\n"
    "For each gate you claim is firing, cite ≥2 ledger events (e####) that directly support it.\n"
    "Output exactly:\n"
    "Gate(s): <comma-separated>\n"
    "→ Evidence [e####, e####; e####, e####]\n"
    "→ Verdict: Reset | No reset\n"
    "→ One action: <imperative sentence>\n"
    "No metrics/traits; no extra commentary."
)
