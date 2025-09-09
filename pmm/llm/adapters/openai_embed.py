"""OpenAI embedding adapter (minimal, no API calls)."""

from __future__ import annotations

from typing import List


class OpenAIEmbed:
    """Tiny placeholder for an OpenAI embedding adapter.

    Stores the model name and exposes an `embed` method signature compatible
    with `EmbeddingAdapter`, but does not perform any network calls.
    """

    def __init__(self, model: str, **kw) -> None:
        self.model = model
        self.kw = kw

    def embed(
        self, texts: List[str]
    ) -> List[List[float]]:  # pragma: no cover - not invoked here
        raise NotImplementedError("OpenAIEmbed.embed not wired in Step 5")
