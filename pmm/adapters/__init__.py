# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/adapters/__init__.py
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Protocol, Union


GenerationStatus = Literal["complete", "empty", "truncated", "indeterminate"]


@dataclass(frozen=True)
class GenerationResult:
    """Provider-neutral result of one model generation."""

    text: str
    status: GenerationStatus
    meta: Dict[str, Any] = field(default_factory=dict)


def normalize_generation_result(
    result: Union[GenerationResult, str],
) -> GenerationResult:
    """Normalize legacy adapters while callers migrate to GenerationResult."""

    if isinstance(result, GenerationResult):
        return result
    if isinstance(result, str):
        status: GenerationStatus = "complete" if result.strip() else "empty"
        return GenerationResult(
            text=result,
            status=status,
            meta={"adapter_contract": "legacy_string"},
        )
    raise TypeError("adapter must return GenerationResult or str")


class LLMAdapter(Protocol):
    """Transport contract for model providers.

    ``system_prompt`` is the complete provider-facing system policy. Adapters
    translate and transmit it without injecting PMM policy of their own.
    """

    def generate_reply(
        self, system_prompt: str, user_prompt: str
    ) -> GenerationResult:  # pragma: no cover - interface
        ...


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)
