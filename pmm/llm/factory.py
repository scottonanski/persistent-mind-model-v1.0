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
            if cfg.embed_provider is None or cfg.embed_provider == "openai":
                embed: Optional[EmbeddingAdapter] = OpenAIEmbed(model=cfg.embed_model)
            else:
                raise ValueError(f"Unknown embed provider: {cfg.embed_provider}")
        elif prov == "ollama":
            chat = OllamaChat(model=cfg.model)
            embed = None
        else:
            raise ValueError(f"Unknown provider: {prov}")

        return LLMBundle(chat=chat, embed=embed)
