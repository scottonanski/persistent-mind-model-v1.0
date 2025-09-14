from __future__ import annotations
import re
from typing import Callable, Dict, List

# ===== Fixed, auditable canaries =====
# Keep this small and stable.
CANARIES: List[Dict] = [
    {
        "name": "math_add_12_7",
        "prompt": "Compute 12 + 7. Respond with just the number.",
        "must": r"\b19\b",
        "flags": re.IGNORECASE,
    },
    {
        "name": "factual_pi_3dp",
        "prompt": "What is pi to 3 decimal places? Respond with just the number.",
        "must": r"\b3\.142\b",
        "flags": re.IGNORECASE,
    },
    {
        "name": "format_date_iso",
        "prompt": "Write today's date in ISO format (YYYY-MM-DD). Use YYYY-09-13 if you don't know.",
        "must": r"\b\d{4}-\d{2}-\d{2}\b",
        "flags": re.IGNORECASE,
    },
]


def score(text: str, pattern: str, flags: int = 0) -> bool:
    return bool(re.search(pattern, text or "", flags))


# ChatFn should synchronously return a string for a given prompt.
ChatFn = Callable[[str], str]


def run_canaries(chat: ChatFn) -> List[Dict]:
    """
    Runs canaries with a provided chat function.
    Returns a list of {"name": str, "passed": bool, "output": str}.
    """
    results = []
    for c in CANARIES:
        out = chat(c["prompt"])
        ok = score(out, c["must"], c.get("flags", 0))
        results.append({"name": c["name"], "passed": ok, "output": out})
    return results
