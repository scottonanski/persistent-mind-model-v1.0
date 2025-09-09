"""OpenAI chat adapter using only the Python standard library (urllib)."""

from __future__ import annotations

import os
import json
from typing import List, Dict, Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIChat:
    """Minimal OpenAI Chat Completions client using urllib."""

    def __init__(self, model: str):
        self.model = model

    def generate(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 1.0,
        max_tokens: int = 512,
        **kw: Any,
    ) -> str:
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
            return data["choices"][0]["message"]["content"]
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
