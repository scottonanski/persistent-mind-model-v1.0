import re
from typing import Dict, Any, List, Tuple, Set

from pmm.storage.eventlog import EventLog


def validate_bot_metrics(
    bot_response: str, actual_metrics: Dict[str, Any], tolerance: float = 0.01
) -> bool:
    """Check if bot-reported IAS/GAS match actual computed metrics (within tolerance).

    Returns True if metrics are consistent (within tolerance) or if no metrics are mentioned.
    Returns False if metrics are mentioned but don't match actual values.
    """
    # Look for IAS=X.XXX, GAS=Y.YYY pattern in response
    match = re.search(r"IAS\s*=\s*([0-9.]+).*GAS\s*=\s*([0-9.]+)", bot_response)
    if not match:
        return True  # no metrics mentioned → not a mismatch

    ias_reported, gas_reported = float(match.group(1)), float(match.group(2))

    # Check if reported values are within tolerance of actual values
    return (
        abs(ias_reported - actual_metrics.get("IAS", 0.0)) <= tolerance
        and abs(gas_reported - actual_metrics.get("GAS", 0.0)) <= tolerance
    )


# --- Strict operator validators and language sanitation ---

_AFFECTIVE_MAP = {
    r"\bconcerned\b": "at issue",
    r"\bexcited\b": "positive",
    r"\bafraid\b": "risk",
    r"\banxious\b": "risk",
    r"\bworried\b": "risk",
    r"\buneasy\b": "risk",
    r"\bstressed\b": "cost",
}


def sanitize_language(text: str) -> str:
    s = text or ""
    for pat, repl in _AFFECTIVE_MAP.items():
        s = re.sub(pat, repl, s, flags=re.IGNORECASE)
    return s


_OBS_RE = re.compile(r"^\s*Observation\s*:\s*(.+?)\s*\n", re.IGNORECASE | re.DOTALL)
_INF_RE = re.compile(r"\bInference\s*:\s*(.+?)\s*\n", re.IGNORECASE | re.DOTALL)
_EVI_RE = re.compile(r"Evidence\s*\[(e\d+),\s*(e\d+)\]", re.IGNORECASE)
_NEXT_RE = re.compile(r"Next\s*step\s*:\s*(.+?)\s*\n", re.IGNORECASE | re.DOTALL)
_TEST_RE = re.compile(r"Test\s*:\s*(.+)$", re.IGNORECASE | re.DOTALL)


def _extract_eids(text: str) -> List[int]:
    return [int(m) for m in re.findall(r"\be(\d{2,})\b", text or "")]


def _eids_exist(eventlog: EventLog, eids: List[int]) -> Tuple[bool, Set[int]]:
    try:
        events = eventlog.read_all()
    except Exception:
        events = []
    have = {int(ev.get("id") or 0) for ev in events if ev.get("id")}
    good = {eid for eid in eids if eid in have}
    return (len(good) >= 2, good)


def _has_observable_clause(s: str) -> bool:
    # Heuristic: presence of a measurable noun or comparator
    return bool(
        re.search(
            r"error|rate|count|citations?|score|≥|<=|>=|≤|at least|within\s+\d+\s+turns",
            s,
            re.IGNORECASE,
        )
    )


def validate_decision_probe(text: str, eventlog: EventLog) -> Tuple[bool, str]:
    # Shape checks
    if not (
        _OBS_RE.search(text)
        and _INF_RE.search(text)
        and _EVI_RE.search(text)
        and _NEXT_RE.search(text)
        and _TEST_RE.search(text)
    ):
        return False, "Malformed: missing required sections"
    if re.search(r"IAS|GAS|Stage|traits?\s*[=:]", text, re.IGNORECASE):
        return False, "Metrics/traits leakage"
    inf = _INF_RE.search(text).group(1)
    if not ("IF" in inf or "if" in inf) or not ("THEN" in inf or "then" in inf):
        return False, "Inference not in IF…THEN form"
    if not _has_observable_clause(inf):
        return False, "Inference lacks observable"
    # Evidence IDs
    m = _EVI_RE.search(text)
    eids = [int(m.group(1)[1:]), int(m.group(2)[1:])] if m else []
    ok, good = _eids_exist(eventlog, eids)
    if not ok:
        return (
            False,
            "INSUFFICIENT EVIDENCE — need valid ledger IDs or concrete observable. Provide 2 real e#### and restate.",
        )
    # Next step and test one sentence each (approx)
    next_line = _NEXT_RE.search(text).group(1).strip()
    test_line = _TEST_RE.search(text).group(1).strip()
    if next_line.count(".") > 1:
        return False, "Next step must be one sentence"
    if not re.search(r"≥|<=|>=|≤|at least\s+\d+|within\s+\d+\s+turns|\d+%", test_line):
        return False, "Test lacks explicit threshold"
    return True, "OK"


def validate_gate_check(text: str, eventlog: EventLog) -> Tuple[bool, str]:
    # Extract fields
    gates_line = None
    evid_line = None
    verdict_line = None
    action_line = None
    for line in (text or "").splitlines():
        if line.lower().startswith("gate(s):"):
            gates_line = line
        elif line.strip().lower().startswith(
            "→ evidence"
        ) or line.strip().lower().startswith("-> evidence"):
            evid_line = line
        elif line.lower().startswith("→ verdict") or line.lower().startswith(
            "-> verdict"
        ):
            verdict_line = line
        elif line.lower().startswith("→ one action") or line.lower().startswith(
            "-> one action"
        ):
            action_line = line
    if not all([gates_line, evid_line, verdict_line, action_line]):
        return False, "Malformed: missing required sections"
    # Parse gates
    allowed = {
        "integrity",
        "drift",
        "contamination",
        "cost/determinism",
        "cost",
        "determinism",
    }
    gates = [
        g.strip().lower()
        for g in re.sub(r"^gate\(s\):", "", gates_line, flags=re.IGNORECASE).split(",")
    ]
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
    # Verdict
    if not re.search(
        r"\b(verdict)\s*:\s*(reset|no\s*reset)\b", verdict_line, re.IGNORECASE
    ):
        return False, "Invalid verdict"
    # One action must be imperative-ish
    if not re.search(r"^\s*(→|->)\s*One action\s*:\s*[A-Za-z]", action_line):
        return False, "Missing action"
    if re.search(r"IAS|GAS|Stage|traits?\s*[=:]", text, re.IGNORECASE):
        return False, "Metrics/traits leakage"
    return True, "OK"


# Strict prompt helpers (for injection)
DECISION_PROBE_PROMPT = (
    "Use ≤2 memgraph relations. Output exactly:\n"
    "Observation (specific, ≤20 words) → Inference (IF…THEN…, falsifiable, mentions observable) → Evidence [e####, e####]\n"
    "→ Next step (1 sentence, concrete, starts with a verb) → Test (1 sentence, explicit pass/fail threshold).\n"
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
