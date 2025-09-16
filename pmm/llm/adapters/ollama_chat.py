"""Ollama chat adapter (minimal, no API calls)."""

from __future__ import annotations

from typing import List, Dict, Any, Optional
import logging

try:
    from pmm.storage.eventlog import EventLog
except ImportError:
    EventLog = None

logger = logging.getLogger(__name__)


class OllamaChat:
    """Tiny placeholder for a local Ollama chat adapter.

    Stores the model name and exposes a `generate` method signature compatible
    with `ChatAdapter`, but does not perform any network calls.
    """

    def __init__(self, model: str, **kw) -> None:
        self.model = model
        self.kw = kw

    def generate(
        self, messages: List[Dict], **kwargs
    ) -> str:  # pragma: no cover - not invoked here
        raise NotImplementedError("OllamaChat.generate not wired in Step 5")


class OllamaChatAdapter:
    def __init__(
        self,
        model: str = "llama3",
        base_url: str = "http://localhost:11434",
        eventlog: Optional["EventLog"] = None,
    ):
        self.model = model
        self.base_url = base_url
        self.eventlog = eventlog
        try:
            import ollama

            self.client = ollama.Client(host=base_url)
        except ImportError:
            logger.error(
                "Ollama library not installed. Please install it with 'pip install ollama'"
            )
            raise

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 300,
    ) -> str:
        try:
            import asyncio

            response = await asyncio.to_thread(
                self.client.chat,
                model=self.model,
                messages=messages,
                options={"temperature": temperature, "num_predict": max_tokens},
                stream=False,
            )
            content = response["message"]["content"]

            # Log interaction to EventLog if available
            if self.eventlog:
                self.eventlog.append(
                    kind="llm_interaction",
                    content="",
                    meta={
                        "model": self.model,
                        "input_messages": messages,
                        "response_content": (
                            content[:100] if len(content) > 100 else content
                        ),
                    },
                )

            return content
        except Exception as e:
            logger.error(f"Error generating response from Ollama: {e}")
            raise
