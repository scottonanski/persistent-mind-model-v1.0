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
        self._server_available = False
        try:
            import requests

            # Get current metrics
            from pmm.runtime.metrics import get_or_compute_ias_gas
            from pmm.storage.eventlog import get_default_eventlog

            eventlog = get_default_eventlog()
            ias, gas = get_or_compute_ias_gas(eventlog)

            url = f"{self.base_url}/api/chat"
            payload = {
                "model": self.model,
                "messages": [],
                "options": {},
                "stream": False,
            }
            headers = {
                "Content-Type": "application/json",
                "X-PMM-IAS": str(ias),
                "X-PMM-GAS": str(gas),
            }

            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()

            logger.info(f"Sent metrics in headers: IAS={ias}, GAS={gas}")
            self._server_available = True
        except ImportError:
            logger.error(
                "requests library not installed. Please install it with 'pip install requests'"
            )
            raise
        except Exception as e:
            logger.warning(f"Ollama server not available at {base_url}: {e}")
            # Don't raise - allow the adapter to be created even if server is down
            self._server_available = False

    def generate(
        self,
        messages: List[Dict],
        temperature: float = 0.7,
        max_tokens: int = 300,
        **kwargs,
    ) -> str:
        """Generate response using Ollama via direct HTTP request."""
        if not self._server_available:
            raise RuntimeError(
                f"Ollama server not available at {self.base_url}. Please start the Ollama server or use a different provider."
            )

        try:
            import requests

            # Get current metrics
            from pmm.runtime.metrics import get_or_compute_ias_gas
            from pmm.storage.eventlog import get_default_eventlog

            eventlog = get_default_eventlog()
            ias, gas = get_or_compute_ias_gas(eventlog)

            url = f"{self.base_url}/api/chat"
            payload = {
                "model": self.model,
                "messages": messages,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    **kwargs,
                },
                "stream": False,
            }
            headers = {
                "Content-Type": "application/json",
                "X-PMM-IAS": str(ias),
                "X-PMM-GAS": str(gas),
            }

            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()

            logger.info(f"Sent metrics in headers: IAS={ias}, GAS={gas}")
            content = data["message"]["content"]
            return f"{content}\n[Current Metrics: IAS={ias:.3f}, GAS={gas:.3f}, Temperature={temperature:.3f}, Max Tokens={max_tokens}]"
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

            # Get current metrics
            from pmm.runtime.metrics import get_or_compute_ias_gas
            from pmm.storage.eventlog import get_default_eventlog

            eventlog = get_default_eventlog()
            ias, gas = get_or_compute_ias_gas(eventlog)

            return f"{content}\n[Current Metrics: IAS={ias:.3f}, GAS={gas:.3f}, Temperature={temperature:.3f}, Max Tokens={max_tokens}]"
        except Exception as e:
            logger.error(f"Error generating response from Ollama: {e}")
            raise
