"""Deterministic dummy chat adapter for tests.

Echoes user input and emits a single well-formed commitment line.
"""

from __future__ import annotations


class DummyAdapter:
    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return f"Echo: {user_prompt}\nCOMMIT: note this item"

    # Deterministic latency hint for diagnostics (ms)
    deterministic_latency_ms: int = 0
