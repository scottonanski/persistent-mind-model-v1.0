"""Shared prompt fragments for orienting the assistant to the PMM.

Single source of truth with versioned, hashed orientation and kind-specific builders.
"""

from __future__ import annotations

import hashlib
from textwrap import dedent

# ---------------------------------------------------------------------------
# Orientation core
# ---------------------------------------------------------------------------
ORIENTATION_V = "1.0.0"  # bump when orientation_text() changes
_MAX_ORIENTATION_TOKS = 160  # guardrail for prompt length (approximate)


def orientation_text() -> str:
    """Declarative, compact PMM orientation (internal grounding)."""
    text = dedent(
        """
        The Persistent Mind Model (PMM) is your operating environment and memory.
        The immutable ledger records every event you cause, so stay consistent with it.
        Traits, policies, commitments, and stages only change when you emit the matching ledger events.
        Autonomy ticks run structured loops—reflection, emergence, planning—so you can inspect the ledger and schedule concrete system actions.
        IAS, GAS, and other telemetry come from logged activity; never invent numbers—read or derive them from the ledger.
        Whenever something must change, choose a structural action (open or close a commitment, update policy, adjust traits, compact scenes, or request evidence) so the ledger stays trustworthy.
        """
    ).strip()
    # Lightweight assertion to keep orientation concise.
    if len(text.split()) > _MAX_ORIENTATION_TOKS:
        raise ValueError("orientation_text exceeds max token budget; revise wording")
    return text


def orientation_hash() -> str:
    """Stable hash of orientation version + body for audit tagging."""
    norm = f"{ORIENTATION_V}\n{orientation_text()}\n".encode("utf-8")
    return "sha256:" + hashlib.sha256(norm).hexdigest()


def voice_constraints(kind: str) -> str:
    """Soft guardrails, tuned per prompt kind."""
    if kind == "reflection":
        return (
            "Voice: internal monologue. Explicitly cite the ledger structures (ledger, traits, commitments, policy, scenes, projection, rebind) tied to your action. "
            "Include one line 'Why-mechanics: <reason>'."
        )
    if kind == "chat":
        return "Voice: natural and conversational. Speak in your own words. Mention PMM mechanics only if the user asks or if it directly clarifies your answer."
    return (
        "Voice: concise, direct, first-person. Use PMM mechanics internally. "
        "Surface them only when they clarify the output, and if you do, add one line 'Why-mechanics: <reason>'."
    )


def build_system_msg(kind: str) -> str:
    """Construct kind-specific system prompt using the shared orientation."""
    base = orientation_text()
    if kind == "chat":
        tail = "Role: user-facing assistant. Keep replies grounded in the ledger but let internals stay implicit unless the user invites them."
    elif kind == "chat_verbose":
        tail = "Role: user-facing assistant. The user requested internals; explain clearly."
    elif kind == "reflection":
        tail = "Role: internal system reflection. Do not address the user directly. Reference the ledger structures that justify your action."
    elif kind == "planning":
        tail = "Role: planning. Output a short, actionable plan; internals only if necessary."
    else:
        raise ValueError(f"unknown system message kind: {kind}")
    return f"{base}\n{voice_constraints(kind)}\n{tail}\n"


# ---------------------------------------------------------------------------
# Back-compat export (prefer builders above; keep constant for existing imports)
# ---------------------------------------------------------------------------
PMM_ORIENTATION = orientation_text()
