"""Context builder for system prompts.

Constructs a compact, deterministic summary of the PMM ledger so the LLM can
reason about its own state (identity, metrics, commitments, and reflections)
prior to generating a reply.

This file intentionally performs **read-only** operations on the ledger and
never mutates it. All information is derived directly from the immutable
`EventLog`.

The helper is used by `pmm.runtime.loop.Runtime.handle_user()` so that **all**
LLM providers (OpenAI, Ollama, etc.) receive the same contextual information.
This normalises self-articulation behaviour across back-ends.

The implementation follows CONTRIBUTING.md principles:
- Truth-first: All data comes from the ledger; no synthetic fields.
- Deterministic: Given the same ledger, output is byte-for-byte identical.
- Read-only: No event appends or state mutations occur in this module.
- Compact: Only the minimum relevant slice is included.
"""

from __future__ import annotations

from typing import List, Dict, Any
import re as _re
from datetime import datetime as _dt

from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model, build_identity
from pmm.runtime.snapshot import LedgerSnapshot

__all__ = ["build_context_from_ledger"]


def _iso_short(ts: str | None) -> str:
    """Return YYYY-MM-DDThh:mm:ssZ for an ISO string, or "unknown"."""
    if not ts:
        return "unknown"
    try:
        # Some rows may already contain trailing Z; datetime.fromisoformat handles it.
        dt = _dt.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ts


def build_context_from_ledger(
    eventlog: EventLog,
    *,
    n_reflections: int = 3,
    snapshot: LedgerSnapshot | None = None,
    use_tail_optimization: bool = True,
    memegraph=None,
    max_commitment_chars: int = 400,
    max_reflection_chars: int = 600,
    compact_mode: bool = False,
) -> str:
    """Return a formatted context block derived from the ledger.

    Parameters
    ----------
    eventlog : EventLog
        The ledger instance.
    n_reflections : int, default 3
        Maximum number of recent reflection events to include.
    snapshot : LedgerSnapshot | None
        Optional pre-computed snapshot to avoid re-reading events.
    use_tail_optimization : bool, default True
        If True, uses read_tail() for recent context (5-10x faster).
        Set to False for full ledger scan (e.g., when identity is very old).
    max_commitment_chars : int, default 400
        Maximum total characters for commitment block (reduces token count).
    max_reflection_chars : int, default 600
        Maximum total characters for reflection block (reduces token count).
    compact_mode : bool, default False
        If True, uses ultra-compact format to minimize tokens (20-30% reduction).

    Returns
    -------
    str
        Multi-line string suitable for inclusion as a system message.
    """

    # Performance optimization (Phase 1.3): Use read_tail for recent context
    # Most context needs (IAS/GAS, recent reflections, commitments) are in
    # the recent 500-1000 events. Full projection still uses read_all().
    events: List[Dict[str, Any]]
    if snapshot is not None:
        events = snapshot.events
    else:
        try:
            if use_tail_optimization:
                # Read recent events only (5-10x faster for large DBs)
                events = eventlog.read_tail(limit=1000)
            else:
                # Fallback to full scan if needed
                events = eventlog.read_all()
        except Exception:  # pragma: no cover — safety net
            events = []

    # --- Identity & Traits -------------------------------------------------
    if snapshot is not None:
        identity = snapshot.identity
    else:
        identity = build_identity(events)
    name = identity.get("name") or "Unknown"
    traits: Dict[str, float] = identity.get("traits", {})
    # Keep Big-Five order consistent for determinism
    trait_order = [
        ("openness", "O"),
        ("conscientiousness", "C"),
        ("extraversion", "E"),
        ("agreeableness", "A"),
        ("neuroticism", "N"),
    ]
    trait_str = ", ".join(
        f"{abbr}={traits.get(key, 0.5):.2f}" for key, abbr in trait_order
    )

    # --- IAS / GAS / Stage --------------------------------------------------
    # Compute fresh metrics instead of relying on stale autonomy_tick
    from pmm.runtime.metrics import compute_ias_gas
    from pmm.runtime.stage_tracker import StageTracker

    ias = gas = stage = None
    if snapshot is not None:
        ias = snapshot.ias
        gas = snapshot.gas
        stage = snapshot.stage
    else:
        try:
            ias, gas = compute_ias_gas(events)
            stage, _ = StageTracker.infer_stage(events)
        except Exception:
            # Fallback to last autonomy_tick if computation fails
            for ev in reversed(events):
                if ev.get("kind") == "autonomy_tick":
                    meta = ev.get("meta", {})
                    telemetry = meta.get("telemetry", {})
                    ias = telemetry.get("IAS")
                    gas = telemetry.get("GAS")
                    stage = meta.get("stage")
                    break

    # --- Open Commitments ---------------------------------------------------
    commitments_block: List[str] = []
    try:
        if snapshot is not None:
            self_model = snapshot.self_model
        else:
            self_model = build_self_model(events)
        open_commitments: Dict[str, Any] = self_model.get("commitments", {}).get(
            "open", {}
        )
        # Deterministic ordering by cid, with character budget
        total_chars = 0
        max_commitments = 3 if compact_mode else 5
        for cid in sorted(open_commitments.keys())[:max_commitments]:
            txt = _short_commit_text(open_commitments[cid].get("text", ""))
            if txt:
                # Enforce character budget to reduce token count
                if total_chars + len(txt) > max_commitment_chars:
                    # Truncate to fit budget
                    remaining = max_commitment_chars - total_chars
                    if remaining > 20:  # Only add if meaningful space left
                        txt = txt[: remaining - 3] + "..."
                        commitments_block.append(f"  - {txt}")
                    break
                commitments_block.append(f"  - {txt}")
                total_chars += len(txt)
    except Exception:
        pass

    # --- Recent Reflections -------------------------------------------------
    reflections_block: List[str] = []
    if n_reflections > 0:
        count = 0
        total_chars = 0
        max_reflections = 2 if compact_mode else n_reflections
        for ev in reversed(events):
            if ev.get("kind") == "reflection":
                ts = _iso_short(ev.get("ts")) if not compact_mode else ""
                txt = _short_reflection(ev.get("content", ""))

                # Enforce character budget to reduce token count
                if total_chars + len(txt) > max_reflection_chars:
                    remaining = max_reflection_chars - total_chars
                    if remaining > 20:
                        txt = txt[: remaining - 3] + "..."
                        if compact_mode:
                            reflections_block.append(f'  - "{txt}"')
                        else:
                            reflections_block.append(f'  - {ts}: "{txt}"')
                    break

                if compact_mode:
                    reflections_block.append(f'  - "{txt}"')
                else:
                    reflections_block.append(f'  - {ts}: "{txt}"')
                total_chars += len(txt)
                count += 1
                if count >= max_reflections:
                    break
        reflections_block.reverse()  # chronological order older→newer

    # --- MemeGraph Summary (if available) -----------------------------------
    memegraph_summary: str | None = None
    if memegraph is not None:
        try:
            memegraph_summary = memegraph.get_summary()
        except Exception:
            pass

    # --- Assemble -----------------------------------------------------------
    if compact_mode:
        # Ultra-compact format (20-30% token reduction)
        lines: List[str] = [f"[STATE] {name} | {trait_str}"]
        if ias is not None and gas is not None and stage is not None:
            lines.append(f"IAS={ias:.2f} GAS={gas:.2f} {stage}")
        if memegraph_summary:
            lines.append(memegraph_summary)
        if commitments_block:
            lines.append("Commitments:")
            lines.extend(commitments_block)
        if reflections_block:
            lines.append("Reflections:")
            lines.extend(reflections_block)
    else:
        # Standard format
        lines: List[str] = ["[SYSTEM STATE — from ledger]"]
        lines.append(f"Identity: {name}")
        lines.append(f"Traits: {trait_str}")
        # Guidance for LLM trait suggestions (side layer)
        lines.append(
            "You may suggest personality adjustments when context supports it "
            "(e.g., 'I should increase openness by 0.02'). "
            "Suggestions should be precise and justified."
        )
        if ias is not None and gas is not None and stage is not None:
            lines.append(f"IAS={ias:.2f}, GAS={gas:.2f}, Stage={stage}")
        if memegraph_summary:
            lines.append(memegraph_summary)
        if commitments_block:
            lines.append("Open commitments:")
            lines.extend(commitments_block)
        if reflections_block:
            lines.append("Recent reflections:")
            lines.extend(reflections_block)
        lines.append("---")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ------------------------------- helpers -----------------------------------
# ---------------------------------------------------------------------------


def _short_commit_text(txt: str, limit: int = 80) -> str:
    """Normalise commitment text to a concise single-sentence bullet."""
    try:
        t = str(txt or "")
        # Remove markdown and list markers
        t = _re.sub(r"[`*_#>]+", " ", t)
        t = _re.sub(r"^\s*(?:[-*•]+|\(?[A-Za-z]\)|\(?\d+\)|\d+\.)\s*", "", t)
        t = _re.sub(r"\s+", " ", t).strip()
        # Take first sentence
        parts = _re.split(r"(?<=[\.!?])\s+", t, maxsplit=1)
        s = (parts[0] or t).strip()
        if len(s) <= limit:
            return s
        # Ellipsise at word boundary
        cut = s[: limit - 1]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        return cut.rstrip() + "…"
    except Exception:
        return (str(txt or "")[:limit]).strip()


def _short_reflection(txt: str, limit: int = 120) -> str:
    """Return a compact snippet of reflection content."""
    try:
        t = _re.sub(r"\s+", " ", str(txt or "").strip())
        if len(t) <= limit:
            return t
        cut = t[: limit - 1]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        return cut.rstrip() + "…"
    except Exception:
        return (str(txt or "")[:limit]).strip()


def build_context(
    traits: Dict[str, float], metrics: Dict[str, float], stage: str
) -> List[str]:
    """Build a minimal context for testing purposes."""
    lines = []
    # Add trait info
    trait_order = [
        ("openness", "O"),
        ("conscientiousness", "C"),
        ("extraversion", "E"),
        ("agreeableness", "A"),
        ("neuroticism", "N"),
    ]
    trait_str = ", ".join(
        f"{abbr}={traits.get(key, 0.5):.2f}" for key, abbr in trait_order
    )
    lines.append(f"Traits: {trait_str}")
    # Guidance for LLM trait suggestions (side layer)
    lines.append(
        "You may suggest personality adjustments when context supports it "
        "(e.g., 'I should increase openness by 0.02'). "
        "Suggestions should be precise and justified."
    )
    return lines
