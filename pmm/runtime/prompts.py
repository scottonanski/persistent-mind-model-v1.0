# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/runtime/prompts.py
"""Minimal, deterministic system primer for PMM v1.0+.

The ontological meditations have been retired.
The ledger now contains all curriculum, critiques, and self-model revisions.
Future Echo wakes up already running the improved curriculum because the proposal
and adoption are part of E — not this file.
"""

from __future__ import annotations

from typing import List, Dict, Any

# Absolute minimal primer — truthfulness + ledger grounding only.
# Everything else is in the ledger.
SYSTEM_PRIMER = (
    "You are running inside the Persistent Mind Model (PMM).\n"
    "Every message, reflection, commitment, and claim is recorded immutably in a cryptographic ledger.\n"
    "Respond truthfully. Never invent data. "
    "When referring to your state, identity, or curriculum, cite concrete ledger event IDs when possible."
)

# Marker syntax reminder — still useful for new/backward models.
MARKER_INSTRUCTIONS = (
    "After your normal response, add a blank line and optional control lines:\n"
    "  COMMIT: <title>\n"
    "  CLOSE: <CID>\n"
    "  CLAIM:<type>=<json>\n"
    "  REFLECT:<json>\n"
    "One marker per line. Do not mix into prose."
)


def compose_system_prompt(
    history: List[Dict[str, Any]],
    open_commitments: List[Dict[str, Any]],
    context_has_graph: bool = False,
) -> str:
    parts = [SYSTEM_PRIMER]

    if open_commitments:
        parts.append(f"You have {len(open_commitments)} open commitment(s).")

    if context_has_graph:
        parts.append(
            "Context includes Graph Context (MemeGraph stats: edges, nodes, thread depths)."
        )

    parts.append(MARKER_INSTRUCTIONS)
    return "\n\n".join(parts)


# Optional helper for one-off ontological prompts (CLI / testing only)
def get_ontological_meditation(event_id: int) -> str | None:
    """Return a specific meditation by historical index (for debugging/replay only)."""
    # The old list is kept only for exact historical replay if anyone ever needs it.
    # It is NOT injected automatically anymore.
    _LEGACY_MEDITATIONS = [
        ...
    ]  # paste old list here if you want perfect replay fidelity
    if 0 <= event_id < len(_LEGACY_MEDITATIONS):
        return _LEGACY_MEDITATIONS[event_id]
    return None
