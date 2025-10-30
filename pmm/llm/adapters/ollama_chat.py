"""Ollama chat adapter (supports local and cloud).

Enhancements:
- Reads OLLAMA_BASE_URL (or PMM_DEFAULT_BASE_URL) to select host
- Adds Authorization Bearer header when OLLAMA_API_KEY is set (for cloud)
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from typing import Any

try:
    from pmm.storage.eventlog import EventLog
except ImportError:
    EventLog = None

logger = logging.getLogger(__name__)


class OllamaChat:
    """Ollama chat adapter for local model inference.

    Provides a synchronous interface compatible with the PMM Runtime.
    """

    def __init__(self, model: str, base_url: str | None = None, **kw) -> None:
        self.model = model
        # Resolve host priority: explicit arg > OLLAMA_BASE_URL > PMM_DEFAULT_BASE_URL > localhost
        resolved_base = (
            base_url
            or os.getenv("OLLAMA_BASE_URL")
            or os.getenv("PMM_DEFAULT_BASE_URL")
            or "http://localhost:11434"
        )
        self.base_url = resolved_base.rstrip("/")
        self.kw = kw
        # Unknown until first call; do not block on startup
        self._server_available = None  # type: bool | None
        # Provider caps cache (populated lazily from /api/show)
        self._provider_caps: dict[str, int] | None = None
        # Optional auth for Ollama Cloud
        api_key = os.getenv("OLLAMA_API_KEY")
        self._auth_headers = (
            {"Authorization": f"Bearer {api_key}"}
            if (api_key and api_key.strip())
            else {}
        )
        # Avoid probing the server here; defer to first real call to reduce false negatives
        # and avoid blocking initialization when the daemon is starting up or requires auth.
        try:
            import requests  # noqa: F401
        except ImportError:
            logger.error(
                "requests library not installed. Please install it with 'pip install requests'"
            )
            raise

    def _ensure_provider_caps(self) -> None:
        """Populate provider caps (max_context, max_output_tokens) from Ollama /api/show.

        Best-effort; on failure leaves caps unset. Runs at most once per instance.
        """
        if self._provider_caps is not None:
            return
        try:
            import requests

            url = f"{self.base_url}/api/show"
            resp = requests.post(url, json={"name": self.model}, timeout=10)
            resp.raise_for_status()
            data = resp.json() if hasattr(resp, "json") else {}
            # Typical fields: {"modelfile": "...", "parameters": "num_ctx 4096 ..."}
            params = str(data.get("parameters") or "")
            num_ctx = None
            # Simple deterministic parse: find token after "num_ctx"
            if "num_ctx" in params:
                try:
                    parts = params.split()
                    for i, tok in enumerate(parts):
                        if tok == "num_ctx" and i + 1 < len(parts):
                            val = int(parts[i + 1])
                            if val > 0:
                                num_ctx = val
                                break
                except Exception:
                    num_ctx = None
            # Fallback: check model_info for various context field patterns
            if num_ctx is None:
                try:
                    cfg = data.get("model_info") or {}
                    # Try standard fields first
                    nc = int(cfg.get("num_ctx") or cfg.get("context") or 0)
                    if nc > 0:
                        num_ctx = nc
                    else:
                        # Try architecture-specific patterns (e.g., "deepseek2.context_length")
                        for key, val in cfg.items():
                            if "context" in key.lower() and isinstance(val, (int, float)):
                                nc = int(val)
                                if nc > 0:
                                    num_ctx = nc
                                    break
                except Exception:
                    num_ctx = None

            if isinstance(num_ctx, int) and num_ctx > 0:
                # Conservative output hint ~ quarter of context, min 512
                out_hint = max(512, min(num_ctx // 4, num_ctx))
                self._provider_caps = {
                    "max_context": int(num_ctx),
                    "max_output_tokens": int(out_hint),
                }
            else:
                self._provider_caps = None
        except Exception:
            self._provider_caps = None

    def generate(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 300,
        **kwargs,
    ) -> object:
        """Generate response using Ollama via direct HTTP request."""
        try:
            import requests

            # Get current metrics
            from pmm.runtime.metrics import get_or_compute_ias_gas
            from pmm.storage.eventlog import get_default_eventlog

            eventlog = get_default_eventlog()
            ias, gas = get_or_compute_ias_gas(eventlog)

            return_usage = bool(kwargs.pop("return_usage", False))
            url = f"{self.base_url}/api/chat"
            # Set conservative num_ctx for cloud models to prevent 502 errors
            options = {
                "temperature": temperature,
                "num_predict": max_tokens,
                **kwargs,
            }

            # Ensure provider caps are loaded
            self._ensure_provider_caps()

            # Add num_ctx if not already specified and we have provider caps
            if "num_ctx" not in options and self._provider_caps:
                max_ctx = self._provider_caps.get("max_context")
                if max_ctx:
                    # Use discovered context size, capped at 8192 for stability
                    options["num_ctx"] = min(max_ctx, 8192)
                    logger.info(
                        f"Set num_ctx={options['num_ctx']} for generate (discovered: {max_ctx})"
                    )

            payload = {
                "model": self.model,
                "messages": messages,
                "options": options,
                "stream": False,
            }
            headers = {
                "Content-Type": "application/json",
                "X-PMM-IAS": str(ias),
                "X-PMM-GAS": str(gas),
            }
            # Add optional auth header for Ollama Cloud
            headers.update(self._auth_headers)

            # One-time provider caps fetch (best-effort)
            self._ensure_provider_caps()

            response = requests.post(url, json=payload, headers=headers, timeout=120)
            response.raise_for_status()
            data = response.json()
            self._server_available = True

            logger.info(f"Sent metrics in headers: IAS={ias}, GAS={gas}")
            content = data["message"]["content"]

            # Structured response (controller/probe path): do not append metrics noise
            if return_usage:
                stop_reason = data.get("done_reason")
                if stop_reason is None:
                    stop_reason = data.get("message", {}).get("stop_reason")
                if stop_reason is None and data.get("done"):
                    stop_reason = "stop"

                usage: dict[str, int] | None = None
                raw_usage = data.get("usage")
                if isinstance(raw_usage, dict):
                    prompt_tokens = int(raw_usage.get("prompt_tokens") or 0)
                    completion_tokens = int(raw_usage.get("completion_tokens") or 0)
                else:
                    prompt_tokens = int(data.get("prompt_eval_count") or 0)
                    completion_tokens = int(data.get("eval_count") or 0)
                if prompt_tokens or completion_tokens:
                    usage = {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                    }

                class _Resp:
                    def __init__(
                        self, text, stop_reason, usage_info, provider_caps=None
                    ):
                        self.text = text
                        self.stop_reason = stop_reason
                        self.usage = usage_info
                        self.provider_caps = (
                            dict(provider_caps) if provider_caps else None
                        )

                return _Resp(
                    content, stop_reason, usage, provider_caps=self._provider_caps
                )

            # Get fresh metrics after response generation (may have changed due to new events)
            fresh_ias, fresh_gas = get_or_compute_ias_gas(eventlog)
            return (
                f"{content}\n[Current Metrics: IAS={fresh_ias:.3f}, "
                f"GAS={fresh_gas:.3f}, Temperature={temperature:.3f}, "
                f"Max Tokens={max_tokens}]"
            )
        except Exception as e:
            self._server_available = False
            # Try to emit status code/body if available
            status = getattr(getattr(e, "response", None), "status_code", None)
            body = None
            try:
                body = getattr(getattr(e, "response", None), "text", None)
                if body and len(body) > 500:
                    body = body[:500]
            except Exception:
                body = None
            if status is not None:
                logger.error(
                    f"Error generating response from Ollama at {self.base_url}: HTTP {status} body={body!r}"
                )
            else:
                logger.error(
                    f"Error generating response from Ollama at {self.base_url}: {e}"
                )
            raise

    def generate_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 300,
        **kwargs,
    ) -> Iterator[str]:
        """Stream response tokens from Ollama.

        Yields tokens as they arrive from the model, providing real-time feedback.
        """
        if self._server_available is False:
            raise RuntimeError(
                f"Ollama server not available at {self.base_url}. Please start "
                f"the Ollama server or use a different provider."
            )

        try:
            import requests

            # Get current metrics
            from pmm.runtime.metrics import get_or_compute_ias_gas
            from pmm.storage.eventlog import get_default_eventlog

            eventlog = get_default_eventlog()
            ias, gas = get_or_compute_ias_gas(eventlog)

            url = f"{self.base_url}/api/chat"
            # Set conservative num_ctx for cloud models to prevent 502 errors
            options = {
                "temperature": temperature,
                "num_predict": max_tokens,
                **kwargs,
            }

            # Ensure provider caps are loaded before streaming
            self._ensure_provider_caps()

            # Add num_ctx if not already specified and we have provider caps
            if "num_ctx" not in options and self._provider_caps:
                max_ctx = self._provider_caps.get("max_context")
                if max_ctx:
                    # Use discovered context size, capped at 8192 for stability
                    options["num_ctx"] = min(max_ctx, 8192)
                    logger.info(
                        f"Set num_ctx={options['num_ctx']} for streaming (discovered: {max_ctx})"
                    )

            payload = {
                "model": self.model,
                "messages": messages,
                "options": options,
                "stream": True,  # Enable streaming
            }

            # Log payload size for debugging large requests
            import json as _json
            payload_size = len(_json.dumps(payload))
            ctx_val = options.get("num_ctx", "not set")
            logger.debug(
                f"Streaming: {len(messages)} msgs, {payload_size}B, num_ctx={ctx_val}"
            )

            headers = {
                "Content-Type": "application/json",
                "X-PMM-IAS": str(ias),
                "X-PMM-GAS": str(gas),
            }
            # Add optional auth header for Ollama Cloud
            headers.update(self._auth_headers)

            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=120,
                stream=True,  # Enable streaming response
            )
            response.raise_for_status()
            self._server_available = True

            logger.info(f"Sent metrics in headers: IAS={ias}, GAS={gas}")

            # Stream tokens as they arrive
            for line in response.iter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            token = data["message"]["content"]
                            if token:  # Only yield non-empty tokens
                                yield token

                        # Check if streaming is done
                        if data.get("done", False):
                            break
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to decode streaming response: {line}")
                        continue

        except Exception as e:
            self._server_available = False
            status = getattr(getattr(e, "response", None), "status_code", None)
            body = None
            try:
                body = getattr(getattr(e, "response", None), "text", None)
                if body and len(body) > 500:
                    body = body[:500]
            except Exception:
                body = None
            if status is not None:
                logger.error(
                    f"Error streaming response from Ollama at {self.base_url}: HTTP {status} body={body!r}"
                )
            else:
                logger.error(
                    f"Error streaming response from Ollama at {self.base_url}: {e}"
                )
            raise


class OllamaChatAdapter:
    def __init__(
        self,
        model: str = "llama3",
        base_url: str = "http://localhost:11434",
        eventlog: EventLog | None = None,
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
        messages: list[dict[str, Any]],
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

            # Get fresh metrics after response generation (may have changed due to new events)
            from pmm.runtime.metrics import get_or_compute_ias_gas
            from pmm.storage.eventlog import get_default_eventlog

            eventlog = get_default_eventlog()
            ias, gas = get_or_compute_ias_gas(eventlog)

            return (
                f"{content}\n[Current Metrics: IAS={ias:.3f}, GAS={gas:.3f}, "
                f"Temperature={temperature:.3f}, Max Tokens={max_tokens}]"
            )
        except Exception as e:
            logger.error(f"Error generating response from Ollama: {e}")
            raise
