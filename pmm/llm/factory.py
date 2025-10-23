"""Unified LLM factory (minimal, provider-agnostic, no API calls)."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np

from pmm.llm.limits import RATE_LIMITED, TickBudget, timed_call

from .adapters.base import ChatAdapter, EmbeddingAdapter
from .adapters.dummy_chat import DummyChat
from .adapters.ollama_chat import OllamaChat
from .adapters.openai_chat import OpenAIChat
from .adapters.openai_embed import OpenAIEmbed


@dataclass
class LLMConfig:
    provider: str
    model: str
    embed_provider: str | None = None
    embed_model: str | None = None
    api_keys: dict[str, str] | None = None


class LLMBundle(NamedTuple):
    chat: ChatAdapter
    embed: EmbeddingAdapter | None


class LLMFactory:
    @staticmethod
    def from_config(cfg: LLMConfig) -> LLMBundle:
        # Choose chat adapter
        prov = (cfg.provider or "").lower()
        if prov == "openai":
            chat: ChatAdapter = OpenAIChat(model=cfg.model)
            if cfg.embed_provider is None or cfg.embed_provider == "openai":
                if "PYTEST_CURRENT_TEST" in os.environ:

                    class MockEmbed(EmbeddingAdapter):
                        def embed(self, texts: list[str]) -> list[list[float]]:
                            return [list(np.zeros(1536)) for _ in texts]

                    embed: EmbeddingAdapter | None = MockEmbed()
                else:
                    embed_model_name = cfg.embed_model or "text-embedding-3-small"
                    embed: EmbeddingAdapter | None = OpenAIEmbed(model=embed_model_name)
            else:
                raise ValueError(f"Unknown embed provider: {cfg.embed_provider}")
        elif prov == "ollama":
            chat = OllamaChat(model=cfg.model)
            embed = None
        elif prov == "dummy":
            chat = DummyChat(model=cfg.model)
            embed = None
        else:
            raise ValueError(f"Unknown provider: {prov}")

        return LLMBundle(chat=chat, embed=embed)


def build_chat(cfg: LLMConfig) -> Callable[[str], str]:
    """Return a simple chat callable f(prompt:str)->str using the configured adapter.

    Deterministic defaults (temperature=0.0, small max_tokens).
    """
    bundle = LLMFactory.from_config(cfg)
    adapter = bundle.chat

    def _call(prompt: str) -> str:
        msgs = [{"role": "user", "content": str(prompt or "")}]
        return adapter.generate(msgs, temperature=0.0, max_tokens=64)

    return _call


def chat_with_budget(
    chat_fn: Callable[[], str],
    *,
    budget: TickBudget,
    tick_id: int | None,
    evlog,
    provider: str,
    model: str,
    log_latency: bool = True,
):
    """Budgeted wrapper for a single chat call.

    Expects chat_fn with no args (bind your prompt at call site).
    Returns RATE_LIMITED sentinel if over budget, else returns the chat output.
    Latency logging should be done at the call site where prompt context is known.
    """
    budget.start_tick(tick_id)
    if not budget.allow_chat():
        try:
            evlog.append(
                kind="rate_limit_skip",
                content="",
                meta={
                    "op": "chat",
                    "provider": str(provider),
                    "model": str(model),
                    "tick": tick_id,
                },
            )
        except Exception:
            pass
        return RATE_LIMITED
    ok, _ms, out = timed_call(lambda: chat_fn())
    # Emit latency only when requested to avoid disturbing event ordering in sensitive paths
    if log_latency:
        try:
            evlog.append(
                kind="llm_latency",
                content="",
                meta={
                    "op": "chat",
                    "provider": str(provider),
                    "model": str(model),
                    "ms": float(_ms),
                    "ok": bool(ok),
                    "tick": tick_id,
                },
            )
        except Exception:
            pass
    if ok:
        return out
    # Propagate exception object for caller to handle deterministically
    return out


def embed_with_budget(
    embed_fn: Callable[[], object],
    *,
    budget: TickBudget,
    tick_id: int | None,
    evlog,
    provider: str,
    model: str,
    log_latency: bool = True,
):
    """Budgeted wrapper for an embed call. Same contract as chat_with_budget."""
    budget.start_tick(tick_id)
    if not budget.allow_embed():
        try:
            evlog.append(
                kind="rate_limit_skip",
                content="",
                meta={
                    "op": "embed",
                    "provider": str(provider),
                    "model": str(model),
                    "tick": tick_id,
                },
            )
        except Exception:
            pass
        return RATE_LIMITED
    ok, _ms, out = timed_call(lambda: embed_fn())
    if log_latency:
        try:
            evlog.append(
                kind="llm_latency",
                content="",
                meta={
                    "op": "embed",
                    "provider": str(provider),
                    "model": str(model),
                    "ms": float(_ms),
                    "ok": bool(ok),
                    "tick": tick_id,
                },
            )
        except Exception:
            pass
    return out
