"""Adapter protocol definitions for chat and embeddings.

Intent:
- Provide minimal, provider-agnostic interfaces for chat and embedding adapters.
- Concrete implementations live in provider-specific modules (OpenAI, Ollama).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol


class ChatAdapter(Protocol):
    def generate(
        self, messages: list[dict], **kwargs
    ) -> str:  # pragma: no cover - interface only
        ...

    def generate_stream(
        self, messages: list[dict], **kwargs
    ) -> Iterator[str]:  # pragma: no cover - interface only
        """Stream response tokens as they're generated.

        Optional method - if not implemented, runtime will fall back to generate().

        Args:
            messages: List of message dictionaries
            **kwargs: Provider-specific options (temperature, max_tokens, etc.)

        Yields:
            Individual tokens or token chunks as strings
        """
        ...


class EmbeddingAdapter(Protocol):
    def embed(
        self, texts: list[str]
    ) -> list[list[float]]:  # pragma: no cover - interface only
        ...
