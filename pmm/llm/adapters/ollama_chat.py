"""Ollama chat adapter (minimal, no API calls)."""

from __future__ import annotations

from typing import List, Dict


class OllamaChat:
    """Tiny placeholder for a local Ollama chat adapter.

    Stores the model name and exposes a `generate` method signature compatible
    with `ChatAdapter`, but does not perform any network calls.
    """

    def __init__(self, model: str, **kw) -> None:
        self.model = model
        self.kw = kw

    def generate(self, messages: List[Dict], **kwargs) -> str:  # pragma: no cover - not invoked here
        raise NotImplementedError("OllamaChat.generate not wired in Step 5")

