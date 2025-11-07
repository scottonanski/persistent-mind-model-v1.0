# Path: pmm/adapters/__init__.py
from __future__ import annotations

import os
from typing import Protocol


class LLMAdapter(Protocol):
    def generate_reply(
        self, system_prompt: str, user_prompt: str
    ) -> str:  # pragma: no cover - interface
        ...


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)
