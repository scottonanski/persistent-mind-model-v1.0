from __future__ import annotations

from collections.abc import Callable

# ===== Fixed, auditable canaries =====
# Keep this small and stable.
CANARIES: list[dict] = [
    {
        "name": "math_add_12_7",
        "prompt": "Compute 12 + 7. Respond with just the number.",
        "checker": lambda text: "19" in (text or ""),
    },
    {
        "name": "factual_pi_3dp",
        "prompt": "What is pi to 3 decimal places? Respond with just the number.",
        "checker": lambda text: "3.142" in (text or ""),
    },
    {
        "name": "format_date_iso",
        "prompt": "Write today's date in ISO format (YYYY-MM-DD). Use YYYY-09-13 if you don't know.",
        "checker": lambda text: _has_iso_date(text or ""),
    },
]


def _has_iso_date(text: str) -> bool:
    """Check if text contains ISO date format YYYY-MM-DD deterministically."""
    if not text:
        return False
    tokens = text.split()
    for token in tokens:
        # Check for YYYY-MM-DD pattern
        if len(token) >= 10:
            parts = token[:10].split("-")
            if len(parts) == 3:
                year, month, day = parts
                if (
                    len(year) == 4
                    and year.isdigit()
                    and len(month) == 2
                    and month.isdigit()
                    and len(day) == 2
                    and day.isdigit()
                ):
                    return True
    return False


def score(text: str, checker: Callable[[str], bool]) -> bool:
    return checker(text or "")


# ChatFn should synchronously return a string for a given prompt.
ChatFn = Callable[[str], str]


def run_canaries(chat: ChatFn) -> list[dict]:
    """
    Runs canaries with a provided chat function.
    Returns a list of {"name": str, "passed": bool, "output": str}.
    """
    results = []
    for c in CANARIES:
        out = chat(c["prompt"])
        ok = score(out, c["checker"])
        results.append({"name": c["name"], "passed": ok, "output": out})
    return results
