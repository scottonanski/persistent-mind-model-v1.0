# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/adapters/dummy_adapter.py
"""Deterministic dummy chat adapter for tests.

Echoes user input and emits a single well-formed commitment line.
"""

from __future__ import annotations

from pmm.adapters import GenerationResult


class DummyAdapter:
    def generate_reply(self, system_prompt: str, user_prompt: str) -> GenerationResult:
        return GenerationResult(
            text=f"Echo: {user_prompt}\nCOMMIT: note this item",
            status="complete",
            meta={"provider": "dummy"},
        )

    # Deterministic latency hint for diagnostics (ms)
    deterministic_latency_ms: int = 0
