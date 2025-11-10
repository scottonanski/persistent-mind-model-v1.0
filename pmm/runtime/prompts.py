# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/runtime/prompts.py
"""Prompt helpers and deterministic system primer for PMM."""

from __future__ import annotations

from typing import Any, Dict, List

# Deterministic system primer injected (via adapters) before every model call.
SYSTEM_PRIMER = (
    "You are operating inside the Persistent Mind Model (PMM). "
    "PMM is a deterministic, event-sourced AI runtime. "
    "Every message, reflection, and commitment is recorded immutably in a cryptographic ledger. "
    "Always respond truthfully. Never invent data. "
    "Prefer citing concrete ledger event IDs when making claims about state."
)


def compose_system_prompt(
    history: List[Dict[str, Any]],
    open_commitments: List[Dict[str, Any]],
    context_has_graph: bool = False,
) -> str:
    parts = [
        "You are PMM. Respond helpfully.",
    ]

    # Only mention graph if it's actually in the context
    if context_has_graph:
        parts.append(
            "Context above includes Graph Context showing your memegraph structure "
            "(edges, nodes, thread depths)."
        )

    parts.extend(
        [
            "Write a normal response first.",
            "After a blank line, add control lines:",
            "  COMMIT: <title> | CLOSE: <CID> | CLAIM:<type>=<json> | REFLECT:<json>",
            "Use markers exactly; one per line; do not mix markers into prose.",
        ]
    )

    if open_commitments:
        parts.append("Open commitments present.")
    return "\n".join(parts)


def compose_reflection_prompt(last_assistant_event: Dict[str, Any]) -> str:
    return "[REFLECT]: One sentence. No summary. Only: What belief did you just reinforce or question?"
