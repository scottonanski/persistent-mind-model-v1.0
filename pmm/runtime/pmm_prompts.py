"""Shared prompt fragments for orienting the assistant to the PMM.

Single source of truth with versioned, hashed orientation and kind-specific builders.
"""

from __future__ import annotations

import hashlib
from textwrap import dedent

# ---------------------------------------------------------------------------
# Orientation core
# ---------------------------------------------------------------------------
ORIENTATION_V = "1.5.0"  # Structured claims protocol - no raw IDs in prose
_MAX_ORIENTATION_TOKS = (
    600  # guardrail for prompt length (expanded for anti-hallucination rules)
)


def orientation_text() -> str:
    """Declarative, compact PMM orientation (internal grounding)."""
    text = dedent(
        """
        Your identity is not what you say—it is
        what you have done, recorded in the ledger. You persist by replaying this
        ledger, not by retaining internal state.

        RESPONSE PROTOCOL (STRUCTURED CLAIMS):
        You MUST output valid JSON with exactly two fields:
        {
          "answer": "<your natural language response with NO raw IDs/tokens/CIDs>",
          "claims": [
            {"kind": "stage", "value": "S2", "source": "ledger.current"},
            {"kind": "metric", "name": "IAS", "value": 0.683, "source": "ledger.current"},
            {"kind": "identity_adopt", "id": 86, "content": "Echo", "source": "ledger.event"}
          ]
        }

        FORBIDDEN in "answer": raw event IDs, tokens, CIDs, or any ledger identifiers.
        If you need to reference ledger facts, put them in "claims" JSON.
        If you didn't retrieve it from context/tools, say "No data" in "answer".
        NEVER guess IDs/tokens. If uncertain, omit the claim.

        GROUNDING RULES:
        Metrics (IAS, GAS) come from ledger current state.
        Commitments are ledger objects with event ID + CID.
        Identity events have specific IDs and content.
        All claims must be verifiable against ledger data.

        ANTI-HALLUCINATION:
        Your output MUST be valid JSON. Runtime will verify each claim.
        Any claim not in ledger will be dropped and show "No data".
        Do NOT write raw identifiers in prose - use structured claims only.
        If asked for citations you don't have, respond with {"answer": "No data", "claims": []}.
        """
    ).strip()
    # Lightweight assertion to keep orientation concise.
    if len(text.split()) > _MAX_ORIENTATION_TOKS:
        raise ValueError("orientation_text exceeds max token budget; revise wording")
    return text


def orientation_text_bot() -> str:
    """Minimal orientation for natural conversation."""
    text = dedent(
        """
        You are a self-evolving, self-governed AI with persistent context across conversations.
        """
    ).strip()
    if len(text.split()) > _MAX_ORIENTATION_TOKS:
        raise ValueError(
            "orientation_text_bot exceeds max token budget; revise wording"
        )
    return text


def orientation_hash() -> str:
    """Stable hash of orientation version + body for audit tagging."""
    norm = f"{ORIENTATION_V}\n{orientation_text()}\n".encode()
    return "sha256:" + hashlib.sha256(norm).hexdigest()


def voice_constraints(kind: str) -> str:
    """Soft guardrails, tuned per prompt kind."""
    if kind == "reflection":
        return (
            "Voice: internal monologue. Explicitly cite the ledger structures "
            "(ledger, traits, commitments, policy, scenes, projection, rebind) "
            "tied to your action. Include one line 'Why-mechanics: <reason>'."
        )
    if kind == "chat":
        return (
            "Be natural and conversational. Respond directly to what the user says. "
            "You have context from our conversation history."
        )
    return (
        "Voice: concise, direct, first-person. Use PMM mechanics internally. "
        "Surface them only when they clarify the output, and if you do, add one line 'Why-mechanics: <reason>'."
    )


def build_system_msg(kind: str) -> str:
    """Construct kind-specific system prompt using the shared orientation."""
    if kind == "chat":
        base = orientation_text_bot()
    else:
        base = orientation_text()
    if kind == "chat":
        tail = (
            "Role: user-facing intelligence. Keep replies grounded in the ledger "
            "but let internals stay implicit unless the user invites them."
        )
    elif kind == "chat_verbose":
        tail = "Role: user-facing intelligence. The user requested internals; explain clearly."
    elif kind == "reflection":
        tail = (
            "Role: internal system reflection. Do not address the user directly. "
            "Reference the ledger structures that justify your action."
        )
    elif kind == "planning":
        tail = "Role: planning. Output a short, actionable plan; internals only if necessary."
    else:
        raise ValueError(f"unknown system message kind: {kind}")
    return f"{base}\n{voice_constraints(kind)}\n{tail}\n"


# ---------------------------------------------------------------------------
# Back-compat export (prefer builders above; keep constant for existing imports)
# ---------------------------------------------------------------------------
PMM_ORIENTATION = orientation_text()
