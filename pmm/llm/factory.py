"""Unified LLM factory (minimal, provider-agnostic, no API calls)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple, Optional, Dict

from .adapters.base import ChatAdapter, EmbeddingAdapter
from .adapters.openai_chat import OpenAIChat
from .adapters.openai_embed import OpenAIEmbed
from .adapters.ollama_chat import OllamaChat


@dataclass
class LLMConfig:
    provider: str
    model: str
    embed_provider: Optional[str] = None
    embed_model: Optional[str] = None
    api_keys: Optional[Dict[str, str]] = None


class LLMBundle(NamedTuple):
    chat: ChatAdapter
    embed: Optional[EmbeddingAdapter]


class LLMFactory:
    @staticmethod
    def from_config(cfg: LLMConfig) -> LLMBundle:
        # Choose chat adapter
        prov = (cfg.provider or "").lower()
        if prov == "openai":
            chat: ChatAdapter = OpenAIChat(model=cfg.model)
        elif prov == "ollama":
            chat = OllamaChat(model=cfg.model)
        else:
            raise ValueError(f"Unknown provider: {cfg.provider}")

        # Choose embedding adapter; may be None
        # Only honor explicit embed_provider; if not provided, no embed adapter.
        eprov = (cfg.embed_provider or "").lower()
        if eprov == "openai":
            if not cfg.embed_model:
                cfg.embed_model = "text-embedding-3-small"
            embed: Optional[EmbeddingAdapter] = OpenAIEmbed(model=cfg.embed_model)
        elif eprov in ("", None):
            embed = None
        else:
            raise ValueError(f"Unknown embed provider: {cfg.embed_provider}")

        return LLMBundle(chat=chat, embed=embed)

