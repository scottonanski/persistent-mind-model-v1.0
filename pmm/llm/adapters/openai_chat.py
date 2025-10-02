"""OpenAI chat adapter using only the Python standard library (urllib)."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIChat:
    """Minimal OpenAI Chat Completions client using urllib."""

    def __init__(self, model: str):
        self.model = model

    def generate(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 1.0,
        max_tokens: int = 512,
        **kw: Any,
    ) -> Any:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set (put it in .env)")

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
        }
        body = json.dumps(payload).encode("utf-8")
        req = Request(
            OPENAI_CHAT_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            finish = data["choices"][0].get("finish_reason")
            usage = data.get("usage") or {}

            # Structured response when requested
            if kw.get("return_usage"):

                class _Resp:
                    def __init__(self, text, stop_reason, usage):
                        self.text = text
                        self.stop_reason = stop_reason
                        self.usage = usage
                        self.provider_caps = None

                return _Resp(content, finish, usage)

            return content
        except HTTPError as e:
            try:
                err_body = e.read().decode("utf-8")[:500]
            except Exception:
                err_body = ""
            raise RuntimeError(
                f"OpenAI HTTP error: {e.code} {e.reason}; body={err_body}"
            ) from e
        except URLError as e:
            raise RuntimeError(f"OpenAI network error: {e.reason}") from e
        except Exception as e:  # pragma: no cover - defensive path
            raise RuntimeError(f"OpenAIChat.generate failed: {e}") from e

    def generate_stream(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 1.0,
        max_tokens: int = 512,
        **kw: Any,
    ) -> Iterator[str]:
        """Stream response tokens from OpenAI.

        Yields tokens as they arrive from the model, providing real-time feedback.
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set (put it in .env)")

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
            "stream": True,  # Enable streaming
        }
        body = json.dumps(payload).encode("utf-8")
        req = Request(
            OPENAI_CHAT_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(req, timeout=30) as resp:
                # Stream Server-Sent Events
                for line in resp:
                    line = line.decode("utf-8").strip()
                    if not line or line == "data: [DONE]":
                        continue

                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])  # Skip "data: " prefix
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {})
                                content = delta.get("content")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue

        except HTTPError as e:
            try:
                err_body = e.read().decode("utf-8")[:500]
            except Exception:
                err_body = ""
            raise RuntimeError(
                f"OpenAI HTTP error: {e.code} {e.reason}; body={err_body}"
            ) from e
        except URLError as e:
            raise RuntimeError(f"OpenAI network error: {e.reason}") from e
        except Exception as e:
            raise RuntimeError(f"OpenAIChat.generate_stream failed: {e}") from e
