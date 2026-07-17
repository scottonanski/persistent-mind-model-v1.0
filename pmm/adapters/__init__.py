# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/adapters/__init__.py
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Protocol, Union


GenerationStatus = Literal["complete", "empty", "truncated", "indeterminate"]
DEFAULT_OUTPUT_BUDGET_TOKENS = 2048


@dataclass(frozen=True)
class GenerationResult:
    """Provider-neutral result of one model generation."""

    text: str
    status: GenerationStatus
    meta: Dict[str, Any] = field(default_factory=dict)


class AdapterTransportError(RuntimeError):
    """Provider transport failed after safe request measurements were known."""

    def __init__(self, category: str, *, meta: Dict[str, Any] | None = None) -> None:
        super().__init__(category)
        self.category = category
        self.meta = dict(meta or {})


def resolve_output_budget_tokens(explicit: int | None = None) -> int | None:
    """Resolve and validate the provider-neutral output budget."""

    raw: Any = explicit
    if raw is None:
        value = os.environ.get("PMM_OUTPUT_BUDGET_TOKENS")
        raw = value if value not in (None, "") else None
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise ValueError("output budget must be a positive integer")
    try:
        budget = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("output budget must be a positive integer") from exc
    if budget <= 0 or (isinstance(raw, str) and str(budget) != raw.strip()):
        raise ValueError("output budget must be a positive integer")
    return budget


def resolve_application_output_budget(
    explicit: int | None = None,
) -> tuple[int, str]:
    """Resolve PMM application policy: override, environment, then fixed default."""

    if explicit is not None:
        budget = resolve_output_budget_tokens(explicit)
        assert budget is not None
        return budget, "argument"
    if os.environ.get("PMM_OUTPUT_BUDGET_TOKENS") not in (None, ""):
        budget = resolve_output_budget_tokens()
        assert budget is not None
        return budget, "environment"
    return DEFAULT_OUTPUT_BUDGET_TOKENS, "pmm_default_v1"


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
    translate and transmit it without injecting PMM policy of their own. An
    adapter must explicitly declare and accept a configured output budget; an
    absent budget preserves compatibility with legacy custom adapters.
    """

    supports_output_budget: bool
    output_budget_tokens: int | None
    output_budget_source: str

    def generate_reply(
        self, system_prompt: str, user_prompt: str
    ) -> GenerationResult:  # pragma: no cover - interface
        ...


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)
