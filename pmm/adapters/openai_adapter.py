# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/adapters/openai_adapter.py
from __future__ import annotations

import os
from pmm.adapters import (
    AdapterTransportError,
    GenerationResult,
    GenerationStatus,
    resolve_output_budget_tokens,
)


class OpenAIAdapter:
    """OpenAI transport for an already complete system prompt.

    Import is deferred to call time to avoid hard dependency during tests.
    """

    supports_output_budget = True

    def __init__(
        self, model: str | None = None, output_budget_tokens: int | None = None
    ) -> None:
        # Prefer explicit arg, then PMM-specific var, then common OPENAI_MODEL
        self.model = (
            model
            or os.environ.get("PMM_OPENAI_MODEL")
            or os.environ.get("OPENAI_MODEL")
            or "gpt-4o-mini"
        )
        self.output_budget_tokens = resolve_output_budget_tokens(output_budget_tokens)

    def generate_reply(
        self, system_prompt: str, user_prompt: str
    ) -> GenerationResult:
        # Lazy import
        try:
            import openai  # type: ignore
        except Exception as e:  # pragma: no cover - import error path
            raise RuntimeError("openai package not available") from e

        system_content = system_prompt
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_prompt},
        ]
        prompt_measurements = {
            "adapter_system_primer_insertions": 0,
            "total_assembled_prompt_chars": len(system_content) + len(user_prompt),
            "context_window_tokens": getattr(self, "context_window_tokens", None),
        }

        client = openai.OpenAI() if hasattr(openai, "OpenAI") else None
        request_budget = (
            {"max_completion_tokens": self.output_budget_tokens}
            if self.output_budget_tokens is not None
            else {}
        )
        if client:
            # new SDK style
            try:
                resp = client.chat.completions.create(
                    model=self.model,
                    temperature=0,
                    top_p=1,
                    messages=messages,
                    **request_budget,
                )
            except Exception as exc:
                raise AdapterTransportError(
                    type(exc).__name__,
                    meta={
                        **prompt_measurements,
                        "provider": "openai",
                        "model": self.model,
                        "temperature": 0,
                        "top_p": 1,
                        "seed": None,
                        "configured_output_budget_tokens": self.output_budget_tokens,
                    },
                ) from exc
            # Deterministic metadata capture
            choice = resp.choices[0]
            text = choice.message.content or ""
            finish_reason = choice.finish_reason
            status: GenerationStatus
            if finish_reason == "length":
                status = "truncated"
            elif finish_reason == "stop" and text.strip():
                status = "complete"
            elif finish_reason == "stop":
                status = "empty"
            else:
                status = "indeterminate"
            generation_meta = {
                **prompt_measurements,
                "provider": "openai",
                "model": self.model,
                "temperature": 0,
                "top_p": 1,
                "seed": None,
                "finish_reason": finish_reason,
                "provider_prompt_tokens": _openai_prompt_tokens(resp),
                "configured_output_budget_tokens": self.output_budget_tokens,
                "provider_output_tokens": _openai_output_tokens(resp),
                "provider_reasoning_tokens": _openai_reasoning_tokens(resp),
                "provider_stop_reason": finish_reason,
                "length_limit_reached": finish_reason == "length",
            }
            return GenerationResult(text=text, status=status, meta=generation_meta)
        else:
            # legacy
            try:
                resp = openai.ChatCompletion.create(
                    model=self.model,
                    temperature=0,
                    top_p=1,
                    messages=messages,
                    **request_budget,
                )
            except Exception as exc:
                raise AdapterTransportError(
                    type(exc).__name__,
                    meta={
                        **prompt_measurements,
                        "provider": "openai",
                        "model": self.model,
                        "temperature": 0,
                        "top_p": 1,
                        "seed": None,
                        "configured_output_budget_tokens": self.output_budget_tokens,
                    },
                ) from exc
            choice = resp["choices"][0]
            text = choice["message"]["content"] or ""
            finish_reason = choice.get("finish_reason")
            if finish_reason == "length":
                status = "truncated"
            elif finish_reason == "stop" and text.strip():
                status = "complete"
            elif finish_reason == "stop":
                status = "empty"
            else:
                status = "indeterminate"
            generation_meta = {
                **prompt_measurements,
                "provider": "openai",
                "model": self.model,
                "temperature": 0,
                "top_p": 1,
                "seed": None,
                "finish_reason": finish_reason,
                "provider_prompt_tokens": _openai_prompt_tokens(resp),
                "configured_output_budget_tokens": self.output_budget_tokens,
                "provider_output_tokens": _openai_output_tokens(resp),
                "provider_reasoning_tokens": _openai_reasoning_tokens(resp),
                "provider_stop_reason": finish_reason,
                "length_limit_reached": finish_reason == "length",
            }
            return GenerationResult(text=text, status=status, meta=generation_meta)


def _openai_prompt_tokens(response) -> int | None:
    """Return provider-reported prompt tokens across SDK response styles."""

    usage = getattr(response, "usage", None)
    value = getattr(usage, "prompt_tokens", None) if usage is not None else None
    if value is None and isinstance(response, dict):
        usage = response.get("usage") or {}
        value = usage.get("prompt_tokens") if isinstance(usage, dict) else None
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _openai_output_tokens(response) -> int | None:
    usage = getattr(response, "usage", None)
    value = getattr(usage, "completion_tokens", None) if usage is not None else None
    if value is None and isinstance(response, dict):
        usage = response.get("usage") or {}
        value = usage.get("completion_tokens") if isinstance(usage, dict) else None
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _openai_reasoning_tokens(response) -> int | None:
    usage = getattr(response, "usage", None)
    details = (
        getattr(usage, "completion_tokens_details", None)
        if usage is not None
        else None
    )
    value = getattr(details, "reasoning_tokens", None) if details is not None else None
    if value is None and isinstance(response, dict):
        usage = response.get("usage") or {}
        details = usage.get("completion_tokens_details") if isinstance(usage, dict) else None
        value = details.get("reasoning_tokens") if isinstance(details, dict) else None
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None
