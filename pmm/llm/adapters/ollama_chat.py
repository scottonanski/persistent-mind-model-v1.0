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
    """Ollama chat adapter for local model inference.

    Provides a synchronous interface compatible with the PMM Runtime.
    """

    def __init__(
        self, model: str, base_url: str = "http://localhost:11434", **kw
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.kw = kw
        try:
            import ollama

            self.client = ollama.Client(host=base_url)
        except ImportError:
            logger.error(
                "Ollama library not installed. Please install it with 'pip install ollama'"
            )
            raise

    def generate(
        self,
        messages: List[Dict],
        temperature: float = 0.7,
        max_tokens: int = 300,
        **kwargs,
    ) -> str:
        """Generate response using Ollama."""
        try:
            response = self.client.chat(
                model=self.model,
                messages=messages,
                options={
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    **kwargs,
                },
                stream=False,
            )
            return response["message"]["content"]
        except Exception as e:
            logger.error(f"Error generating response from Ollama: {e}")
            raise


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
