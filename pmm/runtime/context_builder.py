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

from datetime import datetime as _dt
from typing import Any

try:
    from pmm.runtime.ledger_mirror import LedgerMirror
except Exception:  # pragma: no cover -- optional dependency during bootstrap
    LedgerMirror = None  # type: ignore

from pmm.runtime.snapshot import LedgerSnapshot
from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_identity, build_self_model
from pmm.utils.parsers import extract_first_sentence, normalize_whitespace

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
    mirror: LedgerMirror | None = None,
    n_reflections: int = 3,
    snapshot: LedgerSnapshot | None = None,
    use_tail_optimization: bool = True,
    memegraph=None,
    max_commitment_chars: int = 400,
    max_reflection_chars: int = 600,
    compact_mode: bool = False,
    include_metrics: bool = True,
    include_commitments: bool = True,
    include_reflections: bool = True,
    diagnostics: dict[str, Any] | None = None,
) -> str:
    """Return a formatted context block derived from the ledger.

    Parameters
    ----------
    eventlog : EventLog
        The ledger instance.
    mirror : LedgerMirror | None
        Optional request-scoped mirror. When provided, ledger reads route through it.
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
    # Increase limit when commitments are requested to ensure visibility
    tail_limit = 5000 if include_commitments else 1000
    tail_truncated = False

    diag: dict[str, Any]
    if diagnostics is not None:
        diagnostics.clear()
        diag = diagnostics
    else:
        diag = {}

    diag.update(
        {
            "used_snapshot": snapshot is not None,
            "fallback_full_scan": False,
            "tail_limit": (
                tail_limit if snapshot is None and use_tail_optimization else None
            ),
            "tail_truncated": False,
            "metrics_missing": False,
            "commitments_missing": False,
            "reflections_missing": False,
            "needs_metrics": False,
            "needs_commitments": False,
            "needs_reflections": False,
        }
    )

    def _short_digest(value: str | None) -> str:
        if not value:
            return "none"
        try:
            return str(value)[:12]
        except Exception:
            return "none"

    events: list[dict[str, Any]]
    if snapshot is not None:
        events = snapshot.events
    else:
        try:
            if use_tail_optimization:
                # Read recent events only (5-10x faster for large DBs)
                if mirror is not None:
                    events = mirror.read_tail(limit=tail_limit)
                else:
                    events = eventlog.read_tail(limit=tail_limit)
                diag["tail_limit"] = tail_limit
                if events:
                    try:
                        first_id = int(events[0].get("id") or 0)
                    except Exception:
                        first_id = 0
                    tail_truncated = first_id > 1 or len(events) >= tail_limit
                    diag["tail_truncated"] = tail_truncated
            else:
                # Fallback to full scan if needed
                events = (
                    mirror.read_all() if mirror is not None else eventlog.read_all()
                )
                diag["tail_limit"] = None
        except Exception:  # pragma: no cover — safety net
            events = []

    # --- Identity & Traits -------------------------------------------------
    # Priority: MemeGraph (full history) > Snapshot > Events (tail)

    if snapshot is not None:
        identity = snapshot.identity
    elif memegraph is not None:
        # Use MemeGraph for identity (has full history, no tail truncation)
        try:
            identity_index = memegraph._identity_index
            if identity_index:
                # Get most recent identity name
                name = list(identity_index.keys())[0] if identity_index else "Unknown"
                # Find the identity_adopt event for this name
                # Search through event nodes for identity_adopt kind
                for node in memegraph._nodes.values():
                    if node.label == "event":
                        attrs = node.attrs or {}
                        if attrs.get("kind") == "identity_adopt":
                            # This is an identity adoption event
                            # event id accessible via attrs if needed in future
                            # (not currently used; avoid unused variable warnings)
                            if attrs.get("id"):
                                break  # Use first (earliest) identity adoption
            else:
                name = "Unknown"
            # Still need traits from events (not in MemeGraph yet)
            identity = build_identity(events)
            if name != "Unknown":
                identity["name"] = name  # Override with MemeGraph name
        except Exception:
            # Fallback to event-based identity
            identity = build_identity(events)
    else:
        identity = (
            mirror.get_identity() if mirror is not None else build_identity(events)
        )

    name = identity.get("name") or "Unknown"
    traits: dict[str, float] = identity.get("traits", {})
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

    # --- User Identity -----------------------------------------------------
    # Retrieve user name from ledger (most recent user_identity_set event)
    user_name: str | None = None
    try:
        for ev in reversed(events):
            if ev.get("kind") == "user_identity_set":
                meta = ev.get("meta", {})
                user_name = meta.get("user_name")
                if user_name:
                    break
    except Exception:
        pass

    # If tail slice missed user identity, fall back to full ledger read once.
    fallback_events: list[dict[str, Any]] | None = None
    if (
        user_name is None
        and snapshot is None
        and use_tail_optimization
        and len(events) >= 1000
    ):
        try:
            all_events = (
                mirror.read_all() if mirror is not None else eventlog.read_all()
            )
        except Exception:
            all_events = events
        if len(all_events) > len(events):
            try:
                for ev in reversed(all_events):
                    if ev.get("kind") == "user_identity_set":
                        meta = ev.get("meta", {})
                        candidate = meta.get("user_name")
                        if candidate:
                            fallback_events = all_events
                            user_name = candidate
                            break
            except Exception:
                fallback_events = None

    if fallback_events is not None:
        events = fallback_events
        # Recompute identity/traits deterministically against full ledger
        identity = build_identity(events)
        name = identity.get("name") or "Unknown"
        traits = identity.get("traits", {})
        trait_str = ", ".join(
            f"{abbr}={traits.get(key, 0.5):.2f}" for key, abbr in trait_order
        )

    # --- IAS / GAS / Stage --------------------------------------------------
    # Priority: MemeGraph (full history) > Snapshot > Events (tail)
    from pmm.runtime.metrics import compute_ias_gas
    from pmm.runtime.stage_tracker import StageTracker

    ias = gas = stage = None
    stage_progression: list[str] = []

    stage_entry: dict[str, Any] | None = None
    stage_history_tokens: list[dict[str, Any]] = []

    if snapshot is not None:
        ias = snapshot.ias
        gas = snapshot.gas
        stage = snapshot.stage
    elif memegraph is not None:
        # Use MemeGraph for stage (has full progression history)
        try:
            stage = memegraph.latest_stage()
            stage_history = memegraph.stage_history()
            try:
                stage_entry = memegraph.latest_stage_entry()
            except Exception:
                stage_entry = None
            try:
                stage_history_tokens = memegraph.stage_history_with_tokens(limit=5)
            except Exception:
                stage_history_tokens = []
            if stage_history:
                # Get last 5 stages for progression display
                stage_progression = [h[2] for h in stage_history[-5:]]
            # Still compute IAS/GAS from events (not in MemeGraph)
            ias, gas = compute_ias_gas(events)
        except Exception:
            # Fallback to event-based computation
            ias, gas = compute_ias_gas(events)
            stage, _ = StageTracker.infer_stage(events)
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

    if stage_entry is None and memegraph is not None:
        try:
            stage_entry = memegraph.latest_stage_entry()
        except Exception:
            stage_entry = None
    if not stage_history_tokens and memegraph is not None:
        try:
            stage_history_tokens = memegraph.stage_history_with_tokens(limit=5)
        except Exception:
            stage_history_tokens = []

    # Update diagnostics for metrics
    metrics_missing = include_metrics and (ias is None or gas is None or stage is None)
    diag["metrics_missing"] = metrics_missing
    diag["needs_metrics"] = metrics_missing

    # --- Open Commitments ---------------------------------------------------
    # Anti-hallucination: Inject actual commitment IDs and text from ledger
    commitments_block: list[str] = []
    commitment_events: list[dict] = []
    try:
        if mirror is not None:
            commitment_events = mirror.get_open_commitment_events(max_events=10)
        if not commitment_events and eventlog is not None:
            commitment_events = eventlog.get_open_commitments(limit=10)
        if not commitment_events:
            closed_cids = set()
            for ev in reversed(events):
                if ev.get("kind") in ("commitment_close", "commitment_expire"):
                    cid = (ev.get("meta") or {}).get("cid")
                    if cid:
                        closed_cids.add(cid)
            for ev in reversed(events):
                if ev.get("kind") == "commitment_open":
                    cid = (ev.get("meta") or {}).get("cid")
                    if cid and cid not in closed_cids:
                        commitment_events.append(ev)
                        if len(commitment_events) >= 10:
                            break
            commitment_events.reverse()

        if commitment_events:
            # Normalize dicts from SQL helpers to full events
            normalized: list[dict] = []
            for ev in commitment_events:
                if "kind" in ev:
                    normalized.append(ev)
                    continue
                eid = int(ev.get("id") or 0)
                try:
                    event = eventlog.read_by_ids([eid])[0]
                except Exception:
                    event = {
                        "id": eid,
                        "kind": "commitment_open",
                        "content": ev.get("content", ""),
                        "meta": ev.get("meta", {}),
                    }
                normalized.append(event)
            commitment_events = normalized

        if commitment_events:
            total_chars = 0
            max_commitments = 3 if compact_mode else 5
            for ev in commitment_events[:max_commitments]:
                eid = ev.get("id", "?")
                cid = (ev.get("meta") or {}).get("cid", "")[:8]
                meta_text = (ev.get("meta") or {}).get("text")
                content_text = ev.get("content", "")
                base_text = meta_text if meta_text else content_text
                txt = _short_commitment(base_text)

                if txt:
                    formatted = f"[{eid}:{cid}] {txt}"

                    if total_chars + len(formatted) > max_commitment_chars:
                        remaining = max_commitment_chars - total_chars
                        if remaining > 30:
                            txt_truncated = (
                                txt[: remaining - len(f"[{eid}:{cid}] ") - 3] + "..."
                            )
                            commitments_block.append(
                                f"  - [{eid}:{cid}] {txt_truncated}"
                            )
                        break

                    commitments_block.append(f"  - {formatted}")
                    total_chars += len(formatted)

        if not commitments_block:
            if snapshot is not None:
                self_model = snapshot.self_model
            elif mirror is not None:
                self_model = mirror.get_self_model()
            else:
                self_model = build_self_model(events)
            open_commitments: dict[str, Any] = self_model.get("commitments", {}).get(
                "open", {}
            )
            total_chars = 0
            max_commitments = 3 if compact_mode else 5
            for cid in sorted(open_commitments.keys())[:max_commitments]:
                txt = _short_commitment(open_commitments[cid].get("text", ""))
                if txt:
                    if total_chars + len(txt) > max_commitment_chars:
                        remaining = max_commitment_chars - total_chars
                        if remaining > 20:
                            txt = txt[: remaining - 3] + "..."
                            commitments_block.append(f"  - {txt}")
                        break
                    commitments_block.append(f"  - {txt}")
                    total_chars += len(txt)
    except Exception:
        pass

    # --- Recent Reflections -------------------------------------------------
    reflections_block: list[str] = []
    if n_reflections > 0:
        count = 0
        total_chars = 0
        max_reflections = 2 if compact_mode else n_reflections
        reflection_events = []
        if mirror is not None:
            try:
                reflection_events = mirror.read_tail(limit=5000)
            except Exception:
                reflection_events = []
        if not reflection_events:
            reflection_events = events

        for ev in reversed(reflection_events):
            if ev.get("kind") != "reflection":
                continue
            ts = _iso_short(ev.get("ts")) if not compact_mode else ""
            txt = _short_reflection(ev.get("content", ""))
            token: str | None = None
            if memegraph is not None:
                try:
                    token = memegraph.event_digest(int(ev.get("id") or 0))
                except Exception:
                    token = None

            # Enforce character budget to reduce token count
            if total_chars + len(txt) > max_reflection_chars:
                remaining = max_reflection_chars - total_chars
                if remaining > 20:
                    txt = txt[: remaining - 3] + "..."
                    if compact_mode:
                        line = f'  - "{txt}"'
                    else:
                        line = f'  - {ts}: "{txt}"'
                    if token:
                        line += f" (token={_short_digest(token)})"
                    reflections_block.append(line)
                break

            if compact_mode:
                line = f'  - "{txt}"'
            else:
                line = f'  - {ts}: "{txt}"'
            if token:
                line += f" (token={_short_digest(token)})"
            reflections_block.append(line)
            total_chars += len(txt)
            count += 1
            if count >= max_reflections:
                break
        reflections_block.reverse()

    # Update diagnostics for commitments and reflections
    commitments_missing = include_commitments and not commitments_block
    reflections_missing = include_reflections and not reflections_block
    diag["commitments_missing"] = commitments_missing
    diag["needs_commitments"] = commitments_missing
    diag["reflections_missing"] = reflections_missing
    diag["needs_reflections"] = reflections_missing

    # --- MemeGraph Summary (if available) -----------------------------------
    # Keep structural info for now - Echo was using it accurately
    # TODO: Refactor to semantic-only after understanding what Echo needs
    memegraph_summary: str | None = None
    if memegraph is not None:
        try:
            memegraph_summary = memegraph.get_summary()
        except Exception:
            pass

    # --- Assemble -----------------------------------------------------------
    if compact_mode:
        # Ultra-compact format (20-30% token reduction)
        lines: list[str] = [
            "[SYSTEM STATE — from ledger]",
            f"[STATE] {name} | {trait_str}",
        ]
        # Explicit identity line for deterministic consumers/tests
        lines.append(f"Identity: {name}")
        if user_name:
            lines.append(f"User: {user_name}")
        if (
            include_metrics
            and ias is not None
            and gas is not None
            and stage is not None
        ):
            lines.append(f"IAS={ias:.2f} GAS={gas:.2f} {stage}")
        if stage_entry:
            stage_token = _short_digest(stage_entry.get("stage_digest"))
            stage_event_token = _short_digest(stage_entry.get("event_digest"))
            stage_event_id = stage_entry.get("event_id")
            lines.append(
                f"Stage token: {stage_token} (event {stage_event_id}, token={stage_event_token})"
            )
        if memegraph_summary:
            lines.append(memegraph_summary)
        if include_commitments:
            lines.append("Commitments:")
            if commitments_block:
                lines.extend(commitments_block)
            else:
                lines.append("  (none)")
        if include_reflections and reflections_block:
            lines.append("Reflections:")
            lines.extend(reflections_block)
    else:
        # Minimal format - just essential state, no architecture lectures
        lines: list[str] = ["[SYSTEM STATE — from ledger]"]
        # Explicit identity line for deterministic consumers/tests
        lines.append(f"Identity: {name}")

        # Identity line only
        if name != "Unknown":
            lines.append(f"[You are {name}]")

        if user_name:
            lines.append(f"[User: {user_name}]")

        if (
            include_metrics
            and ias is not None
            and gas is not None
            and stage is not None
        ):
            # Include stage progression if available from MemeGraph
            if stage_progression:
                progression_str = " → ".join(stage_progression)
                lines.append(f"IAS={ias:.2f}, GAS={gas:.2f}, Stage={stage}")
                lines.append(f"Stage progression: {progression_str}")
            else:
                lines.append(f"IAS={ias:.2f}, GAS={gas:.2f}, Stage={stage}")
        if stage_entry:
            stage_token = _short_digest(stage_entry.get("stage_digest"))
            stage_event_token = _short_digest(stage_entry.get("event_digest"))
            stage_event_id = stage_entry.get("event_id")
            lines.append(
                f"Stage evidence: token={stage_token} via event {stage_event_id} (event_token={stage_event_token})"
            )
        elif stage_history_tokens:
            latest = stage_history_tokens[-1]
            lines.append(
                "Stage evidence: token={stage_digest} via event {event_id} (event_token={event_digest})".format(
                    stage_digest=_short_digest(latest.get("stage_digest")),
                    event_id=latest.get("event_id"),
                    event_digest=_short_digest(latest.get("event_digest")),
                )
            )
        else:
            lines.append(
                "Ledger metrics (IAS/GAS, commitments, reflections) available on request."
            )
        if memegraph_summary:
            lines.append(memegraph_summary)
        if include_commitments:
            lines.append("Open commitments:")
            if commitments_block:
                lines.extend(commitments_block)
            else:
                lines.append("  (none)")
        if include_reflections and reflections_block:
            lines.append("Recent reflections:")
            lines.extend(reflections_block)
        if include_reflections:
            lines.append("---")

    if diagnostics is not None:
        diagnostics.clear()
        diagnostics.update(diag)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ------------------------------- helpers -----------------------------------
# ---------------------------------------------------------------------------


def _short_commitment(txt: str, limit: int = 120) -> str:
    """Return a compact snippet of commitment content (deterministic)."""
    try:
        t = str(txt or "")

        # Try to extract the actual commitment/action line
        # Look for patterns like "Action:", "Commitment:", "Action Proposal:", etc.
        action_keywords = ["action:", "commitment:", "action proposal:"]

        for keyword in action_keywords:
            # Check both plain and markdown bold versions
            for prefix in [keyword, f"**{keyword.rstrip(':')}**:"]:
                idx = t.lower().find(prefix.lower())
                if idx >= 0:
                    # Extract text after the keyword
                    start = idx + len(prefix)
                    rest = t[start:].lstrip()
                    # Take until newline
                    newline_idx = rest.find("\n")
                    if newline_idx > 0:
                        action_text = rest[:newline_idx].strip()
                    else:
                        action_text = rest.strip()

                    # Clean up markdown
                    action_text = _clean_markdown(action_text)
                    action_text = normalize_whitespace(action_text)

                    # Take first sentence
                    s = extract_first_sentence(action_text)

                    if len(s) <= limit:
                        return s
                    # Truncate at word boundary
                    return _truncate_at_word(s, limit)

        # Fallback: skip IAS/GAS lines and take first meaningful sentence
        lines = [line.strip() for line in t.split("\n") if line.strip()]
        for line in lines:
            # Skip lines that are just metrics (deterministic check)
            line_lower = line.lower()
            if any(
                line_lower.startswith(prefix)
                for prefix in [
                    "ias:",
                    "ias ",
                    "gas:",
                    "gas ",
                    "stage:",
                    "stage ",
                    "reflection:",
                ]
            ):
                continue
            if line:
                # Clean and truncate
                line = _clean_markdown(line)
                line = normalize_whitespace(line)
                if len(s) <= limit:
                    return s
                return _truncate_at_word(s, limit)

        # Last resort: just take first sentence
        t = normalize_whitespace(t)
        s = extract_first_sentence(t)
        if len(s) <= limit:
            return s
        return _truncate_at_word(s, limit)
    except Exception:
        return (txt or "")[:limit]


def _clean_markdown(text: str) -> str:
    """Remove markdown formatting characters deterministically."""
    result = []
    for char in text:
        if char not in "`*_#>":
            result.append(char)
        else:
            result.append(" ")
    return "".join(result)


def _truncate_at_word(text: str, limit: int) -> str:
    """Truncate text at word boundary deterministically."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip() + "…"


def _short_reflection(txt: str, limit: int = 120) -> str:
    """Return a compact snippet of reflection content."""
    try:
        t = normalize_whitespace(str(txt or ""))
        if len(t) <= limit:
            return t
        cut = t[: limit - 1]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        return cut.rstrip() + "…"
    except Exception:
        return (str(txt or "")[:limit]).strip()


def build_context(
    traits: dict[str, float], metrics: dict[str, float], stage: str
) -> list[str]:
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
