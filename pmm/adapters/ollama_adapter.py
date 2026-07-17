# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/adapters/ollama_adapter.py
from __future__ import annotations

import json
import os
from urllib import request

from pmm.adapters import (
    AdapterTransportError,
    GenerationResult,
    GenerationStatus,
    resolve_output_budget_tokens,
)


class OllamaAdapter:
    """Ollama transport for an already complete system prompt."""

    supports_output_budget = True

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        output_budget_tokens: int | None = None,
    ) -> None:
        self.model = model or os.environ.get("PMM_OLLAMA_MODEL", "llama3")
        self.base_url = base_url or os.environ.get(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )
        self.output_budget_tokens = resolve_output_budget_tokens(output_budget_tokens)

    def generate_reply(
        self, system_prompt: str, user_prompt: str
    ) -> GenerationResult:
        prompt = f"{system_prompt}\nUser: {user_prompt}\nAssistant:"
        prompt_measurements = {
            "adapter_system_primer_insertions": 0,
            "total_assembled_prompt_chars": len(prompt),
            "context_window_tokens": getattr(self, "context_window_tokens", None),
        }
        options = {"temperature": 0}
        if self.output_budget_tokens is not None:
            options["num_predict"] = self.output_budget_tokens
        body = {
            "model": self.model,
            "prompt": prompt,
            "options": options,
            "stream": False,
        }
        # Record generation params deterministically
        generation_meta = {
            "provider": "ollama",
            "model": self.model,
            "temperature": 0,
            "top_p": None,
            "seed": None,
            "configured_output_budget_tokens": self.output_budget_tokens,
        }
        data = json.dumps(body).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(
                req, timeout=180
            ) as resp:  # pragma: no cover (network in CI)
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise AdapterTransportError(
                type(exc).__name__,
                meta={**generation_meta, **prompt_measurements},
            ) from exc

        text = payload.get("response", "")
        if not isinstance(text, str):
            text = ""
        done = payload.get("done")
        done_reason = payload.get("done_reason")
        if done is True and done_reason == "length":
            status: GenerationStatus = "truncated"
        elif done is True and done_reason == "stop" and text.strip():
            status = "complete"
        elif done is True and done_reason == "stop":
            status = "empty"
        else:
            status = "indeterminate"

        thinking = payload.get("thinking")
        meta = {
            **generation_meta,
            **prompt_measurements,
            "done": done,
            "done_reason": done_reason,
            "prompt_eval_count": payload.get("prompt_eval_count"),
            "provider_prompt_tokens": payload.get("prompt_eval_count"),
            "eval_count": payload.get("eval_count"),
            "provider_output_tokens": payload.get("eval_count"),
            "provider_reasoning_tokens": None,
            "provider_stop_reason": done_reason,
            "length_limit_reached": done_reason == "length",
            "total_duration": payload.get("total_duration"),
            "load_duration": payload.get("load_duration"),
            "prompt_eval_duration": payload.get("prompt_eval_duration"),
            "eval_duration": payload.get("eval_duration"),
            "thinking_present": isinstance(thinking, str) and bool(thinking),
            "thinking_char_count": len(thinking) if isinstance(thinking, str) else 0,
        }
        return GenerationResult(text=text, status=status, meta=meta)
