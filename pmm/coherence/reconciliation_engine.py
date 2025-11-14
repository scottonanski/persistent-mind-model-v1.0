# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/coherence/reconciliation_engine.py
"""Reconciliation action proposals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from pmm.coherence.fragmentation_detector import Conflict


@dataclass(frozen=True)
class ReconciliationAction:
    action_type: str  # "deprecate_both"
    conflict: Conflict


def propose_reconciliation_actions(
    conflicts: List[Conflict],
) -> List[ReconciliationAction]:
    """Propose actions: default to deprecate both."""
    return [ReconciliationAction("deprecate_both", conflict) for conflict in conflicts]
