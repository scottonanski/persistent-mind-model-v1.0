# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/meta_learning/meta_policy.py
"""Meta-policy representations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class MetaPolicy:
    reflection_interval_delta: int
    max_policy_update_rate: float


def meta_policy_from_dict(data: Dict[str, Any]) -> MetaPolicy:
    """Deserialize MetaPolicy from dict."""
    return MetaPolicy(
        reflection_interval_delta=data.get("reflection_interval_delta", 0),
        max_policy_update_rate=data.get("max_policy_update_rate", 0.1),
    )


def meta_policy_to_dict(policy: MetaPolicy) -> Dict[str, Any]:
    """Serialize MetaPolicy to dict."""
    return {
        "reflection_interval_delta": policy.reflection_interval_delta,
        "max_policy_update_rate": policy.max_policy_update_rate,
    }
