"""OpenAI chat adapter (minimal, no API calls)."""

from __future__ import annotations

from typing import List, Dict


class OpenAIChat:
    """Tiny placeholder for an OpenAI chat adapter.

    Stores the model name and exposes a `generate` method signature compatible
    with `ChatAdapter`, but does not perform any network calls.
    """

    def __init__(self, model: str, **kw) -> None:
        self.model = model
        self.kw = kw

    def generate(self, messages: List[Dict], **kwargs) -> str:  # pragma: no cover - not invoked here
        raise NotImplementedError("OpenAIChat.generate not wired in Step 5")

