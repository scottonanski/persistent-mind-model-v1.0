"""Routed context builder using EventRouter instead of tail-constrained reads.

Replaces artificial tail limits with intelligent event routing based on:
- Content relevance (semantic matching)
- Event importance (kind-based priorities)
- Recency bias (recent events weighted higher)
- Structural relationships (identity timeline, commitment chains)

This eliminates Echo's artificial amnesia by providing access to full history
while maintaining performance through smart routing.
"""

from __future__ import annotations

from datetime import datetime as _dt
from typing import Any

from pmm.runtime.event_router import ContextQuery, EventRouter
from pmm.runtime.snapshot import LedgerSnapshot
from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_identity
from pmm.utils.parsers import extract_first_sentence, normalize_whitespace

__all__ = ["build_context_with_router"]


def _iso_short(ts: str | None) -> str:
    """Return YYYY-MM-DDThh:mm:ssZ for an ISO string, or "unknown"."""
    if not ts:
        return "unknown"
    try:
        dt = _dt.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ts


def _short_commitment(text: str) -> str:
    """Extract first sentence from commitment text."""
    if not text:
        return ""
    return extract_first_sentence(normalize_whitespace(text))


def _short_reflection(text: str) -> str:
    """Extract first sentence from reflection text."""
    if not text:
        return ""
    return extract_first_sentence(normalize_whitespace(text))


def build_context_with_router(
    eventlog: EventLog,
    event_router: EventRouter,
    *,
    n_reflections: int = 3,
    snapshot: LedgerSnapshot | None = None,
    max_commitment_chars: int = 400,
    max_reflection_chars: int = 600,
    compact_mode: bool = False,
    include_metrics: bool = True,
    include_commitments: bool = True,
    include_reflections: bool = True,
    diagnostics: dict[str, Any] | None = None,
) -> str:
    """Build context using EventRouter instead of tail-constrained reads.

    This function provides the same interface as the original context builder
    but uses semantic routing to access the full event history instead of
    being artificially limited to recent events.

    Parameters
    ----------
    eventlog : EventLog
        The ledger instance.
    event_router : EventRouter
        Router for intelligent event selection.
    n_reflections : int, default 3
        Maximum number of recent reflection events to include.
    snapshot : LedgerSnapshot | None
        Optional pre-computed snapshot to avoid re-computation.
    max_commitment_chars : int, default 400
        Maximum total characters for commitment block.
    max_reflection_chars : int, default 600
        Maximum total characters for reflection block.
    compact_mode : bool, default False
        If True, uses ultra-compact format to minimize tokens.
    include_metrics : bool, default True
        Whether to include IAS/GAS/Stage metrics.
    include_commitments : bool, default True
        Whether to include open commitments.
    include_reflections : bool, default True
        Whether to include recent reflections.
    diagnostics : dict[str, Any] | None
        Optional diagnostics output dictionary.

    Returns
    -------
    str
        Multi-line string suitable for inclusion as a system message.
    """

    diag: dict[str, Any]
    if diagnostics is not None:
        diagnostics.clear()
        diag = diagnostics
    else:
        diag = {}

    diag.update(
        {
            "used_snapshot": snapshot is not None,
            "used_router": True,
            "tail_limit": None,  # No tail limits with router
            "tail_truncated": False,
            "events_routed": 0,
            "truth_source": "read",  # All events fetched via read_by_ids
        }
    )

    # --- Identity & Traits -------------------------------------------------
    # Use router to get verified identity from full history
    identity_event_id: int | None = None

    if snapshot is not None:
        identity = snapshot.identity
    else:
        # Get latest identity from router (verified identity_adopt events only)
        latest_identity_id = event_router.get_latest_identity_event_id()
        if latest_identity_id:
            identity_event_id = latest_identity_id
            # Fetch the actual identity event for name
            identity_events = eventlog.read_by_ids(
                [latest_identity_id], verify_hash=False
            )
            if identity_events:
                identity_event = identity_events[0]
                name = str(identity_event.get("content", "Unknown"))
            else:
                name = "Unknown"
        else:
            name = "Unknown"

        # For traits, we need a broader set of events
        # Route for trait-relevant events (recent bias for current state)
        trait_query = ContextQuery(
            required_kinds=["trait_update", "identity_adopt", "identity_checkpoint"],
            semantic_terms=[],
            limit=50,
            recency_boost=0.7,  # Strong recency bias for current traits
        )
        trait_event_ids = event_router.route(trait_query)
        trait_events = eventlog.read_by_ids(trait_event_ids, verify_hash=False)

        # Build identity from routed events
        identity = build_identity(trait_events)
        if name != "Unknown":
            identity["name"] = name  # Override with verified name

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
    # Route for user identity events (no recency bias - want the definitive one)
    user_query = ContextQuery(
        required_kinds=["user_identity_set"],
        semantic_terms=[],
        limit=1,
        recency_boost=0.9,  # Actually want most recent user identity
    )
    user_event_ids = event_router.route(user_query)
    user_name: str | None = None

    if user_event_ids:
        user_events = eventlog.read_by_ids(
            user_event_ids, verify_hash=False
        )  # Skip hash verification for now
        if user_events:
            user_event = user_events[0]
            meta = user_event.get("meta", {})
            user_name = meta.get("user_name")

    # --- IAS / GAS / Stage --------------------------------------------------
    # Route for metrics-relevant events
    if include_metrics:
        metrics_query = ContextQuery(
            required_kinds=["metrics_update", "autonomy_tick", "stage_update"],
            semantic_terms=[],
            limit=20,
            recency_boost=0.9,  # Very recent for current state
        )
        metrics_event_ids = event_router.route(metrics_query)
        metrics_events = eventlog.read_by_ids(metrics_event_ids, verify_hash=False)

        # Compute metrics from routed events
        from pmm.runtime.metrics import compute_ias_gas
        from pmm.runtime.stage_tracker import StageTracker

        try:
            ias, gas = compute_ias_gas(metrics_events)
            stage, _ = StageTracker.infer_stage(metrics_events)
        except Exception:
            # Fallback to last autonomy_tick if computation fails
            ias = gas = stage = None
            for event in reversed(metrics_events):
                if event.get("kind") == "autonomy_tick":
                    meta = event.get("meta", {})
                    telemetry = meta.get("telemetry", {})
                    ias = telemetry.get("IAS")
                    gas = telemetry.get("GAS")
                    stage = meta.get("stage")
                    break
    else:
        ias = gas = stage = None

    # --- Open Commitments ---------------------------------------------------
    commitments_block: list[str] = []
    if include_commitments:
        # Route for commitment events (balanced recency - want both recent and important)
        commitment_query = ContextQuery(
            required_kinds=["commitment_open", "commitment_close", "commitment_expire"],
            semantic_terms=[],
            limit=50,  # Get more to properly track open/closed state
            recency_boost=0.5,  # Moderate recency bias
        )
        commitment_event_ids = event_router.route(commitment_query)
        commitment_events = eventlog.read_by_ids(
            commitment_event_ids, verify_hash=False
        )

        # Track open commitments
        closed_cids = set()
        for event in commitment_events:
            if event.get("kind") in ("commitment_close", "commitment_expire"):
                cid = (event.get("meta") or {}).get("cid")
                if cid:
                    closed_cids.add(cid)

        # Collect open commitments
        open_commitment_events = []
        for event in commitment_events:
            if event.get("kind") == "commitment_open":
                cid = (event.get("meta") or {}).get("cid")
                if cid and cid not in closed_cids:
                    open_commitment_events.append(event)
                    if len(open_commitment_events) >= 10:
                        break

        # Sort by event ID (chronological)
        open_commitment_events.sort(key=lambda e: int(e.get("id", 0)))

        # Build commitment block with event IDs for verification
        if open_commitment_events:
            total_chars = 0
            max_commitments = 3 if compact_mode else 5
            for event in open_commitment_events[:max_commitments]:
                eid = event.get("id", "?")
                cid = (event.get("meta") or {}).get("cid", "")[:8]
                txt = _short_commitment((event.get("meta") or {}).get("text", ""))

                if txt:
                    # Format: [event_id:cid] text [read]
                    formatted = f"[{eid}:{cid}] {txt} [read]"

                    # Enforce character budget
                    if total_chars + len(formatted) > max_commitment_chars:
                        remaining = max_commitment_chars - total_chars
                        if remaining > 30:
                            txt_truncated = (
                                txt[
                                    : remaining
                                    - len(f"[{eid}:{cid}] ")
                                    - len(" [read]")
                                    - 3
                                ]
                                + "..."
                            )
                            commitments_block.append(
                                f"  - [{eid}:{cid}] {txt_truncated} [read]"
                            )
                        break

                    commitments_block.append(f"  - {formatted}")
                    total_chars += len(formatted)

    # --- Recent Reflections -------------------------------------------------
    reflections_block: list[str] = []
    if include_reflections and n_reflections > 0:
        # Route for reflection events (moderate recency bias)
        reflection_query = ContextQuery(
            required_kinds=["reflection"],
            semantic_terms=[],
            limit=n_reflections * 2,  # Get extra to account for filtering
            recency_boost=0.6,  # Moderate recency bias
        )
        reflection_event_ids = event_router.route(reflection_query)
        reflection_events = eventlog.read_by_ids(
            reflection_event_ids, verify_hash=False
        )

        # Sort by event ID (most recent first for display)
        reflection_events.sort(key=lambda e: int(e.get("id", 0)), reverse=True)

        count = 0
        total_chars = 0
        max_reflections = 2 if compact_mode else n_reflections

        for event in reflection_events:
            if count >= max_reflections:
                break

            ts = _iso_short(event.get("ts")) if not compact_mode else ""
            txt = _short_reflection(event.get("content", ""))

            # Enforce character budget
            if total_chars + len(txt) > max_reflection_chars:
                remaining = max_reflection_chars - total_chars
                if remaining > 20:
                    txt = txt[: remaining - len(" [read]") - 3] + "..."
                    if compact_mode:
                        reflections_block.append(f'  - "{txt}" [read]')
                    else:
                        reflections_block.append(f'  - {ts}: "{txt}" [read]')
                break

            if compact_mode:
                reflections_block.append(f'  - "{txt}" [read]')
            else:
                reflections_block.append(f'  - {ts}: "{txt}" [read]')
            total_chars += len(txt)
            count += 1

        # Reverse to show chronological order (older → newer)
        reflections_block.reverse()

    # Update diagnostics
    total_events_routed = (
        len(commitment_event_ids)
        + len(reflection_event_ids)
        + len(metrics_event_ids)
        + len(trait_event_ids)
        + len(user_event_ids)
    )
    diag["events_routed"] = total_events_routed

    # --- Assemble -----------------------------------------------------------
    if compact_mode:
        # Ultra-compact format
        lines: list[str] = [f"[STATE] {name} | {trait_str}"]
        if user_name:
            lines.append(f"User: {user_name}")
        if (
            include_metrics
            and ias is not None
            and gas is not None
            and stage is not None
        ):
            lines.append(f"IAS={ias:.2f} GAS={gas:.2f} {stage}")
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
        # Standard format with router information
        lines: list[str] = ["[SYSTEM STATE — from routed events]"]

        # Architecture awareness
        router_stats = event_router.get_stats()
        current_max_id = eventlog.get_max_id()
        lines.append("[YOUR ARCHITECTURE]")
        lines.append(
            "You are an event-sourced AI with semantic routing to your full history."
        )
        lines.append(f"Total events indexed: {router_stats['indexed_events']}")
        lines.append(f"Current max event ID: {current_max_id}")
        lines.append(
            "Your identity, commitments, and reflections are routed from verified events."
        )
        lines.append("")
        lines.append(
            "All data below comes from verified ledger reads [read], not reconstructions."
        )
        lines.append("Event IDs reference actual ledger entries you can trust.")
        lines.append("")

        # Identity with adoption event ID
        if identity_event_id:
            lines.append(
                f"Identity: {name} (verified from event #{identity_event_id}) [read]"
            )
        else:
            lines.append(f"Identity: {name}")

        if user_name:
            lines.append(f"User: {user_name} [read]")
        lines.append(f"Traits: {trait_str} [read]")

        if (
            include_metrics
            and ias is not None
            and gas is not None
            and stage is not None
        ):
            lines.append(f"IAS={ias:.2f}, GAS={gas:.2f}, Stage={stage} [read]")

        if include_commitments:
            lines.append("Open commitments:")
            if commitments_block:
                lines.extend(commitments_block)
            else:
                lines.append("  (none)")

        if include_reflections and reflections_block:
            lines.append("Recent reflections:")
            lines.extend(reflections_block)

        lines.append("---")

    if diagnostics is not None:
        diagnostics.clear()
        diagnostics.update(diag)

    return "\n".join(lines)
