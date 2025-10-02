"""Projection snapshot system for PMM.

Implements deterministic, verifiable snapshots of projection state to enable
O(k) rebuilds instead of O(n) full replays.

Design:
- Snapshots stored in separate table (compressed with zstd)
- Ledger events contain only pointers (keeps ledger lean)
- Canonical checksums ensure verifiability
- Schema versioning prevents drift on upgrades
- Deterministic triggers (exact multiples of interval)

Conforms to CONTRIBUTING.md:
- Ledger integrity: snapshots reproducible from events
- Determinism: fixed intervals, canonical hashing
- Idempotency: creating snapshot twice = no-op
- No env gates: configuration via code constants
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Dict, List, Optional, Tuple

import zstandard as zstd

from pmm.storage.eventlog import EventLog

# Import projection logic directly to avoid circular dependency with cache
# We need the raw projection function, not the cached version
import pmm.storage.projection as projection_module

logger = logging.getLogger(__name__)

# Configuration (fixed constants, no env vars)
SNAPSHOT_SCHEMA_VERSION = "v1.0"
SNAPSHOT_INTERVAL = 1000  # Events between snapshots
SNAPSHOT_ENABLED = True  # Feature flag
SNAPSHOT_RETENTION_COUNT = 10  # Keep last N snapshots
SNAPSHOT_MIN_RETENTION = 5  # Never prune if fewer than this exist


def _build_self_model_raw(events: List[Dict], **kwargs) -> Dict:
    """Build self-model using raw projection logic (bypass cache).

    This avoids circular dependency: snapshot → build_self_model → cache → snapshot
    """
    # Call the actual projection logic directly from the module
    # This bypasses the caching layer in projection.py
    # Apply events using projection logic
    from pmm.config import USE_PROJECTION_CACHE

    old_cache_setting = USE_PROJECTION_CACHE

    try:
        # Temporarily disable caching
        import pmm.config

        pmm.config.USE_PROJECTION_CACHE = False

        # Now call build_self_model - it won't use cache
        result = projection_module.build_self_model(events, eventlog=None, **kwargs)
        return result
    finally:
        # Restore cache setting
        pmm.config.USE_PROJECTION_CACHE = old_cache_setting


def _compute_canonical_checksum(events: List[Dict]) -> str:
    """Compute deterministic checksum of event sequence.

    Hashes canonical tuple (id, kind, meta_hash) for each event.
    Order-sensitive and metadata-sensitive.

    Args:
        events: List of event dicts

    Returns:
        Checksum string like "sha256:abc123..."
    """
    hasher = hashlib.sha256()

    for ev in sorted(events, key=lambda e: e["id"]):  # Ensure order
        # Canonical tuple: (id, kind, meta_hash)
        meta_hash = _hash_dict(ev.get("meta", {}))
        canonical = (ev["id"], ev["kind"], meta_hash)

        # Serialize deterministically (sorted keys)
        canonical_bytes = json.dumps(canonical, sort_keys=True).encode("utf-8")
        hasher.update(canonical_bytes)

    return f"sha256:{hasher.hexdigest()}"


def _hash_dict(d: dict) -> str:
    """Compute deterministic hash of dict (sorted keys)."""
    canonical = json.dumps(d, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _compress_state(state: Dict) -> bytes:
    """Compress projection state with zstd."""
    state_json = json.dumps(state, sort_keys=True)
    compressor = zstd.ZstdCompressor(level=3)  # Fast compression
    return compressor.compress(state_json.encode("utf-8"))


def _decompress_state(compressed: bytes) -> Dict:
    """Decompress projection state from zstd."""
    decompressor = zstd.ZstdDecompressor()
    state_json = decompressor.decompress(compressed).decode("utf-8")
    return json.loads(state_json)


def _ensure_snapshots_table(eventlog: EventLog) -> None:
    """Create snapshots table if it doesn't exist."""
    conn = eventlog._conn
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL UNIQUE,
            schema_version TEXT NOT NULL,
            state_compressed BLOB NOT NULL,
            checksum TEXT NOT NULL,
            created_ts TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_snapshots_event_id ON snapshots(event_id DESC)"
    )
    conn.commit()


def _store_snapshot(
    eventlog: EventLog,
    event_id: int,
    schema_version: str,
    state_compressed: bytes,
    checksum: str,
) -> int:
    """Store compressed snapshot in database."""
    from datetime import datetime, timezone

    _ensure_snapshots_table(eventlog)

    conn = eventlog._conn
    cursor = conn.execute(
        """
        INSERT INTO snapshots (event_id, schema_version, state_compressed, checksum, created_ts)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            event_id,
            schema_version,
            state_compressed,
            checksum,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    return cursor.lastrowid


def _load_snapshot_state(eventlog: EventLog, snapshot_db_id: int) -> bytes:
    """Load compressed state from snapshots table."""
    _ensure_snapshots_table(eventlog)

    cursor = eventlog._conn.execute(
        "SELECT state_compressed FROM snapshots WHERE id = ?", (snapshot_db_id,)
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Snapshot {snapshot_db_id} not found")
    return row[0]


def _find_snapshot_at(eventlog: EventLog, event_id: int) -> Optional[Dict]:
    """Find snapshot event at exact event_id."""
    events = eventlog.read_all()
    for ev in reversed(events):
        if ev.get("kind") == "projection_snapshot":
            meta = ev.get("meta", {})
            if meta.get("anchor_event_id") == event_id:
                return ev
    return None


def _find_latest_snapshot_before(eventlog: EventLog, target_id: int) -> Optional[Dict]:
    """Find most recent snapshot before target_id."""
    events = eventlog.read_all()
    latest = None
    latest_anchor = 0

    for ev in reversed(events):
        if ev.get("kind") == "projection_snapshot":
            meta = ev.get("meta", {})
            anchor = meta.get("anchor_event_id", 0)
            if anchor <= target_id and anchor > latest_anchor:
                latest = ev
                latest_anchor = anchor

    return latest


def should_create_snapshot(eventlog: EventLog) -> Tuple[bool, int]:
    """Determine if snapshot should be created.

    Deterministic: creates snapshots at exact multiples of SNAPSHOT_INTERVAL.

    Returns:
        (should_create, target_event_id)
    """
    if not SNAPSHOT_ENABLED:
        return False, 0

    max_id = eventlog.get_max_id()

    # Round down to nearest interval
    target_id = (max_id // SNAPSHOT_INTERVAL) * SNAPSHOT_INTERVAL

    if target_id == 0:
        return False, 0  # Not enough events yet

    # Check if snapshot already exists at this exact target
    existing = _find_snapshot_at(eventlog, target_id)
    if existing:
        # Check schema compatibility
        existing_version = existing.get("meta", {}).get("schema_version")
        if existing_version == SNAPSHOT_SCHEMA_VERSION:
            return False, target_id  # Already snapshotted with current schema
        else:
            # Schema mismatch, need to rebuild
            logger.info(
                f"Schema version mismatch at event {target_id}: "
                f"{existing_version} → {SNAPSHOT_SCHEMA_VERSION}. Will rebuild snapshot."
            )

    return True, target_id


def create_snapshot(eventlog: EventLog, target_event_id: int, memegraph=None) -> int:
    """Create snapshot at target_event_id.

    Idempotent: creating snapshot twice at same ID with same schema = no-op.

    Args:
        eventlog: EventLog instance
        target_event_id: Event ID to snapshot at (should be multiple of SNAPSHOT_INTERVAL)
        memegraph: Optional MemeGraphProjection instance to include in snapshot

    Returns:
        Event ID of snapshot pointer event
    """
    # Check if compatible snapshot already exists
    existing = _find_snapshot_at(eventlog, target_event_id)
    if existing:
        existing_version = existing.get("meta", {}).get("schema_version")
        if existing_version == SNAPSHOT_SCHEMA_VERSION:
            logger.debug(f"Snapshot at event {target_event_id} already exists")
            return existing["id"]

    # Build state from scratch (deterministic)
    all_events = eventlog.read_all()
    events_to_snapshot = [e for e in all_events if e["id"] <= target_event_id]

    if not events_to_snapshot:
        raise ValueError(f"No events found up to {target_event_id}")

    logger.info(
        f"Creating snapshot at event {target_event_id} ({len(events_to_snapshot)} events)"
    )

    # Build projection state (use raw projection, bypass cache to avoid recursion)
    state = _build_self_model_raw(events_to_snapshot)

    # Include MemeGraph state if available
    if memegraph is not None:
        try:
            state["memegraph"] = memegraph.export_state()
            logger.debug(
                f"Included MemeGraph state: {memegraph.node_count} nodes, "
                f"{memegraph.edge_count} edges"
            )
        except Exception as e:
            logger.warning(f"Failed to export MemeGraph state: {e}")

    # Compute checksum
    checksum = _compute_canonical_checksum(events_to_snapshot)

    # Compress state
    state_compressed = _compress_state(state)

    # Store in snapshots table
    snapshot_db_id = _store_snapshot(
        eventlog=eventlog,
        event_id=target_event_id,
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        state_compressed=state_compressed,
        checksum=checksum,
    )

    # Emit pointer event in ledger
    snapshot_event_id = eventlog.append(
        kind="projection_snapshot",
        content=f"Snapshot at event {target_event_id} (schema {SNAPSHOT_SCHEMA_VERSION})",
        meta={
            "snapshot_id": f"snap_{target_event_id}",
            "anchor_event_id": target_event_id,
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "checksum": checksum,
            "storage": "snapshots_table",
            "snapshot_db_id": snapshot_db_id,
            "event_count": len(events_to_snapshot),
        },
    )

    logger.info(
        f"Snapshot created: event {snapshot_event_id}, "
        f"anchor {target_event_id}, "
        f"compressed size {len(state_compressed)} bytes"
    )

    # Prune old snapshots to maintain bounded storage
    try:
        prune_metrics = prune_old_snapshots(eventlog)
        if prune_metrics["pruned_count"] > 0:
            logger.info(
                f"Pruned {prune_metrics['pruned_count']} old snapshots, "
                f"kept {prune_metrics['retained_count']}, "
                f"freed ~{prune_metrics['storage_freed_kb']}KB"
            )
    except Exception as e:
        logger.warning(f"Snapshot pruning failed: {e}")

    return snapshot_event_id


def prune_old_snapshots(eventlog: EventLog) -> Dict:
    """Prune old snapshots to maintain bounded storage.

    Keeps last SNAPSHOT_RETENTION_COUNT snapshots. Older snapshots are deleted
    from the snapshots table, but pointer events remain in ledger for audit trail.

    Args:
        eventlog: EventLog instance

    Returns:
        Metrics dict with pruning statistics
    """
    # Get all snapshot events from ledger
    all_events = eventlog.read_all()
    snapshot_events = [e for e in all_events if e.get("kind") == "projection_snapshot"]

    if len(snapshot_events) <= SNAPSHOT_MIN_RETENTION:
        # Don't prune if below minimum retention
        return {
            "total_snapshots": len(snapshot_events),
            "pruned_count": 0,
            "retained_count": len(snapshot_events),
            "storage_freed_kb": 0,
            "oldest_retained_event_id": (
                snapshot_events[0]["meta"]["anchor_event_id"] if snapshot_events else 0
            ),
            "newest_retained_event_id": (
                snapshot_events[-1]["meta"]["anchor_event_id"] if snapshot_events else 0
            ),
        }

    # Sort by anchor_event_id (oldest first)
    snapshot_events.sort(key=lambda e: e.get("meta", {}).get("anchor_event_id", 0))

    # Determine which to prune (keep last N)
    to_prune = snapshot_events[:-SNAPSHOT_RETENTION_COUNT]
    to_retain = snapshot_events[-SNAPSHOT_RETENTION_COUNT:]

    if not to_prune:
        return {
            "total_snapshots": len(snapshot_events),
            "pruned_count": 0,
            "retained_count": len(to_retain),
            "storage_freed_kb": 0,
            "oldest_retained_event_id": to_retain[0]["meta"]["anchor_event_id"],
            "newest_retained_event_id": to_retain[-1]["meta"]["anchor_event_id"],
        }

    # Calculate storage freed (estimate)
    storage_freed_kb = 0
    _ensure_snapshots_table(eventlog)

    for snap_event in to_prune:
        snapshot_db_id = snap_event.get("meta", {}).get("snapshot_db_id")
        if not snapshot_db_id:
            continue

        # Get size before deleting
        try:
            cursor = eventlog._conn.execute(
                "SELECT length(state_compressed) FROM snapshots WHERE id = ?",
                (snapshot_db_id,),
            )
            row = cursor.fetchone()
            if row:
                storage_freed_kb += row[0] // 1024  # Convert bytes to KB
        except Exception:
            pass

        # Delete from snapshots table
        try:
            eventlog._conn.execute(
                "DELETE FROM snapshots WHERE id = ?", (snapshot_db_id,)
            )
        except Exception as e:
            logger.warning(f"Failed to delete snapshot {snapshot_db_id}: {e}")

    eventlog._conn.commit()

    metrics = {
        "total_snapshots": len(snapshot_events),
        "pruned_count": len(to_prune),
        "retained_count": len(to_retain),
        "storage_freed_kb": storage_freed_kb,
        "oldest_retained_event_id": to_retain[0]["meta"]["anchor_event_id"],
        "newest_retained_event_id": to_retain[-1]["meta"]["anchor_event_id"],
    }

    logger.debug(
        f"Snapshot pruning: {metrics['pruned_count']} pruned, "
        f"{metrics['retained_count']} retained, "
        f"range [{metrics['oldest_retained_event_id']}..{metrics['newest_retained_event_id']}]"
    )

    return metrics


def build_self_model_optimized(
    events: List[Dict],
    *,
    eventlog: EventLog = None,
    memegraph=None,
    verify_snapshot: bool = False,
    **kwargs,
) -> Dict:
    """Build projection model using snapshot + delta replay.

    Falls back to full replay if:
    - No eventlog provided
    - No snapshots exist
    - Schema version mismatch

    Args:
        events: List of events to build model from
        eventlog: EventLog instance (required for snapshots)
        verify_snapshot: If True, verify snapshot integrity (expensive)
        **kwargs: Passed to build_self_model

    Returns:
        Projection state dict
    """
    if not eventlog or not SNAPSHOT_ENABLED:
        return _build_self_model_raw(events, **kwargs)

    if not events:
        return _build_self_model_raw(events, **kwargs)

    target_id = events[-1]["id"]

    # Find latest snapshot before target
    snapshot_event = _find_latest_snapshot_before(eventlog, target_id)

    if not snapshot_event:
        logger.debug("No snapshot found, using full replay")
        return _build_self_model_raw(events, **kwargs)

    # Check schema compatibility
    snapshot_meta = snapshot_event.get("meta", {})
    snapshot_version = snapshot_meta.get("schema_version")

    if snapshot_version != SNAPSHOT_SCHEMA_VERSION:
        logger.warning(
            f"Snapshot schema mismatch: {snapshot_version} vs current {SNAPSHOT_SCHEMA_VERSION}. "
            f"Falling back to full replay."
        )
        return _build_self_model_raw(events, **kwargs)

    # Load compressed state
    snapshot_db_id = snapshot_meta.get("snapshot_db_id")
    anchor_id = snapshot_meta.get("anchor_event_id")

    try:
        state_compressed = _load_snapshot_state(eventlog, snapshot_db_id)
        base_state = _decompress_state(state_compressed)
    except Exception as e:
        logger.error(f"Failed to load snapshot {snapshot_db_id}: {e}")
        return _build_self_model_raw(events, **kwargs)

    # Restore MemeGraph state if available
    if memegraph is not None and "memegraph" in base_state:
        try:
            memegraph.import_state(base_state["memegraph"])
            logger.debug(
                f"Restored MemeGraph state: {memegraph.node_count} nodes, "
                f"{memegraph.edge_count} edges"
            )
        except Exception as e:
            logger.warning(f"Failed to restore MemeGraph state: {e}")

    # Verify snapshot integrity if requested
    if verify_snapshot:
        logger.info(f"Verifying snapshot integrity at event {anchor_id}")
        if not verify_snapshot_integrity(eventlog, snapshot_event):
            logger.error("Snapshot verification failed, falling back to full replay")
            return _build_self_model_raw(events, **kwargs)

    # Replay delta events
    delta_events = [e for e in events if e["id"] > anchor_id]

    if not delta_events:
        logger.debug(f"Snapshot exact match at event {anchor_id}")
        # Remove memegraph from return state (it's already restored to the instance)
        result = base_state.copy()
        result.pop("memegraph", None)
        return result

    logger.debug(
        f"Using snapshot at {anchor_id}, replaying {len(delta_events)} delta events"
    )

    # Replay delta on top of snapshot
    return _replay_delta(base_state, delta_events, eventlog=eventlog, **kwargs)


def _replay_delta(
    base_state: Dict, delta_events: List[Dict], *, eventlog: EventLog = None, **kwargs
) -> Dict:
    """Replay delta events on top of base state.

    Applies delta events incrementally to the snapshot baseline, preserving
    the accumulated state from the snapshot.

    Args:
        base_state: Snapshot state to start from
        delta_events: Events to apply on top of base_state
        eventlog: EventLog instance (unused, for signature compatibility)
        **kwargs: Additional arguments (unused, for signature compatibility)

    Returns:
        Updated state after applying delta events
    """
    import copy

    # Start from deep copy of the snapshot baseline
    model = copy.deepcopy(base_state)

    # Remove memegraph from model if present (it's already restored separately)
    model.pop("memegraph", None)

    # Incrementally apply each delta event on top of baseline
    # This reuses the same logic as projection.py but operates on existing state
    import re as _re

    name_pattern = _re.compile(r"Name\s+changed\s+to:\s*(?P<name>.+)", _re.IGNORECASE)

    key_map = {
        "o": "openness",
        "openness": "openness",
        "c": "conscientiousness",
        "conscientiousness": "conscientiousness",
        "e": "extraversion",
        "extraversion": "extraversion",
        "a": "agreeableness",
        "agreeableness": "agreeableness",
        "n": "neuroticism",
        "neuroticism": "neuroticism",
    }

    for ev in delta_events:
        kind = ev.get("kind")
        content = ev.get("content", "")
        meta = ev.get("meta") or {}

        if kind == "identity_change":
            new_name = meta.get("name")
            if not new_name:
                m = name_pattern.search(content or "")
                if m:
                    new_name = m.group("name").strip()
            if new_name:
                model["identity"]["name"] = new_name

        elif kind == "identity_adopt":
            new_name = meta.get("name") or content or None
            if isinstance(new_name, str):
                nm = new_name.strip()
                model["identity"]["name"] = nm or None

        elif kind == "identity_clear":
            model["identity"]["name"] = None

        elif kind == "trait_update":
            delta_field = meta.get("delta")
            trait = str(meta.get("trait") or "").strip().lower()

            if isinstance(delta_field, dict) and not trait:
                # Multi-delta schema
                for k, v in delta_field.items():
                    tkey = key_map.get(str(k).lower())
                    if not tkey:
                        continue
                    try:
                        delta_f = float(v)
                    except Exception:
                        delta_f = 0.0
                    cur = float(model["identity"]["traits"].get(tkey, 0.5))
                    newv = max(0.0, min(1.0, cur + delta_f))
                    model["identity"]["traits"][tkey] = newv
            else:
                # Single-trait legacy schema
                try:
                    delta_f = float(delta_field)
                except Exception:
                    delta_f = 0.0
                tkey = key_map.get(trait)
                if tkey:
                    cur = float(model["identity"]["traits"].get(tkey, 0.5))
                    newv = max(0.0, min(1.0, cur + delta_f))
                    model["identity"]["traits"][tkey] = newv

        elif kind == "commitment_open":
            cid = meta.get("cid")
            text = meta.get("text")
            if cid and text is not None:
                entry = {k: v for k, v in meta.items()}
                model["commitments"]["open"][cid] = entry

        elif kind in ("commitment_close", "commitment_expire"):
            cid = meta.get("cid")
            if cid and cid in model["commitments"]["open"]:
                if kind == "commitment_expire":
                    model["commitments"]["expired"][cid] = {
                        "text": model["commitments"]["open"][cid].get("text"),
                        "expired_at": int(ev.get("id") or 0),
                        "reason": (meta or {}).get("reason") or "timeout",
                    }
                model["commitments"]["open"].pop(cid, None)

        elif kind == "commitment_snooze":
            cid = meta.get("cid")
            if cid and cid in model["commitments"]["open"]:
                try:
                    until_t = int(meta.get("until_tick") or 0)
                except Exception:
                    until_t = 0
                model["commitments"]["open"][cid]["snoozed_until"] = until_t

    return model


def verify_snapshot_integrity(eventlog: EventLog, snapshot_event: Dict) -> bool:
    """Verify snapshot matches full replay from scratch.

    Expensive operation - only use in audit mode.

    Returns:
        True if snapshot is valid
    """
    meta = snapshot_event.get("meta", {})
    anchor_id = meta.get("anchor_event_id")
    stored_checksum = meta.get("checksum")
    snapshot_db_id = meta.get("snapshot_db_id")

    # Load stored state
    try:
        state_compressed = _load_snapshot_state(eventlog, snapshot_db_id)
        stored_state = _decompress_state(state_compressed)
    except Exception as e:
        logger.error(f"Failed to load snapshot for verification: {e}")
        return False

    # Rebuild from scratch
    all_events = eventlog.read_all()
    events_to_anchor = [e for e in all_events if e["id"] <= anchor_id]
    fresh_state = _build_self_model_raw(events_to_anchor)
    fresh_checksum = _compute_canonical_checksum(events_to_anchor)

    # Compare checksums
    checksum_match = stored_checksum == fresh_checksum

    # Compare states (deep equality)
    state_match = _deep_equal(stored_state, fresh_state)

    if not checksum_match:
        logger.error(
            f"Snapshot checksum mismatch at event {anchor_id}: "
            f"stored={stored_checksum}, fresh={fresh_checksum}"
        )

    if not state_match:
        logger.error(f"Snapshot state mismatch at event {anchor_id}")

    return checksum_match and state_match


def _deep_equal(a, b) -> bool:
    """Deep equality check for nested dicts/lists."""
    if not isinstance(a, type(b)):
        return False

    if isinstance(a, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_deep_equal(a[k], b[k]) for k in a.keys())

    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(_deep_equal(a[i], b[i]) for i in range(len(a)))

    return a == b
