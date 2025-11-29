# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/adapters/ollama_adapter.py
from __future__ import annotations

import json
import os
from urllib import request


from pmm.runtime.prompts import SYSTEM_PRIMER


class OllamaAdapter:
    """Ollama local model adapter via HTTP API."""

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or os.environ.get("PMM_OLLAMA_MODEL", "llama3")
        self.base_url = base_url or os.environ.get(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )
        self.generation_meta = {
            "provider": "ollama",
            "model": self.model,
            "temperature": 0,
            "top_p": None,
            "seed": None,
        }

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        prompt = f"{SYSTEM_PRIMER}\n\n{system_prompt}\nUser: {user_prompt}\nAssistant:"
        body = {
            "model": self.model,
            "prompt": prompt,
            "options": {"temperature": 0},
            "stream": False,
        }
        # Record generation params deterministically
        self.generation_meta = {
            "provider": "ollama",
            "model": self.model,
            "temperature": 0,
            "top_p": None,
            "seed": None,
        }
        data = json.dumps(body).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(
            req, timeout=180
        ) as resp:  # pragma: no cover (network in CI)
            payload = json.loads(resp.read().decode("utf-8"))
            return payload.get("response", "")
