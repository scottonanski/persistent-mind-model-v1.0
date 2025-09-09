"""Adapter protocol definitions for chat and embeddings.

Intent:
- Provide minimal, provider-agnostic interfaces for chat and embedding adapters.
- Concrete implementations live in provider-specific modules (OpenAI, Ollama).
"""

from __future__ import annotations

from typing import Protocol, List, Dict


class ChatAdapter(Protocol):
    def generate(
        self, messages: List[Dict], **kwargs
    ) -> str:  # pragma: no cover - interface only
        ...


class EmbeddingAdapter(Protocol):
    def embed(
        self, texts: List[str]
    ) -> List[List[float]]:  # pragma: no cover - interface only
        ...
