"""OpenAI chat adapter (minimal HTTP implementation)."""

from __future__ import annotations

import os
import json
from typing import List, Dict, Any

import requests


OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIChat:
    """Minimal OpenAI Chat Completions client using requests."""

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
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(OPENAI_CHAT_URL, headers=headers, data=json.dumps(payload), timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except requests.HTTPError as e:  # type: ignore[attr-defined]
            raise RuntimeError(
                f"OpenAI HTTP error: {e}, body={getattr(e.response, 'text', '')[:500]}"
            ) from e
        except Exception as e:  # pragma: no cover - defensive path
            raise RuntimeError(f"OpenAIChat.generate failed: {e}") from e
