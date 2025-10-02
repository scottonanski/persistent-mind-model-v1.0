"""Incremental projection cache for performance optimization.

Intent:
- Cache the result of build_self_model() and apply only new events
- Preserve all stateful tracking (evidence_seen, identity_adopted)
- Periodic verification against full rebuild for correctness
- Feature-flagged for safe rollback

This module provides 5-50x speedup for projection operations by avoiding
full event log scans on every call.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from typing import Any

from pmm.storage.projection import (
    MAX_TRAIT_DELTA,
    ProjectionInvariantError,
    build_self_model,
)

# Import snapshot support (optional - graceful degradation if not available)
try:
    from pmm.storage.snapshot import (
        SNAPSHOT_ENABLED,
        build_self_model_optimized,
        create_snapshot,
        should_create_snapshot,
    )

    _SNAPSHOT_AVAILABLE = True
except ImportError:
    _SNAPSHOT_AVAILABLE = False
    SNAPSHOT_ENABLED = False

logger = logging.getLogger(__name__)


class ProjectionCache:
    """Incremental projection cache with verification.

    Maintains cached projection state and applies only new events since
    last computation. Periodically verifies against full rebuild.

    Thread-safety: Not thread-safe. Caller must ensure single-threaded access.
    """

    def __init__(
        self,
        *,
        verify_every: int = 1000,
        strict: bool = False,
        max_trait_delta: float = MAX_TRAIT_DELTA,
    ):
        """Initialize projection cache.

        Parameters
        ----------
        verify_every : int, default 1000
            Verify cache against full rebuild every N events.
            Set to 0 to disable verification (not recommended).
        strict : bool, default False
            Enable strict mode for projection invariants.
        max_trait_delta : float
            Maximum trait delta per event.
        """
        self._last_id: int = 0
        self._cached_model: dict | None = None

        # Stateful tracking that must be preserved across incremental updates
        self._evidence_seen: set[tuple[str, str]] = set()  # (cid, evidence_type)
        self._identity_adopted: bool = False
        self._last_eid: int = 0

        # Configuration
        self._verify_every = verify_every
        self._strict = strict
        self._max_trait_delta = max_trait_delta
        self._events_processed = 0

        # Statistics
        self._cache_hits = 0
        self._cache_misses = 0
        self._verifications_passed = 0
        self._verifications_failed = 0

    def get_model(
        self, eventlog, *, on_warn: Callable[[dict], None] | None = None
    ) -> dict:
        """Get cached model, applying only new events.

        Parameters
        ----------
        eventlog : EventLog
            The event log to read from.
        on_warn : callable, optional
            Warning callback for non-strict mode.

        Returns
        -------
        dict
            Self-model with identity and commitments.
        """
        # Check for new events
        new_events = eventlog.read_after_id(after_id=self._last_id, limit=10000)

        if not new_events:
            if self._cached_model is None:
                # First call with empty DB - this is a miss
                self._cache_misses += 1
                return self._initialize_empty_model()
            # Cache hit - no new events
            self._cache_hits += 1
            return copy.deepcopy(self._cached_model)

        # Cache miss - need to process new events
        self._cache_misses += 1

        if self._cached_model is None:
            # First time - build from scratch
            logger.debug(
                f"ProjectionCache: Initial build from {len(new_events)} events"
            )
            all_events = eventlog.read_all()

            # Use snapshot-optimized build if available
            if _SNAPSHOT_AVAILABLE and SNAPSHOT_ENABLED:
                self._cached_model = build_self_model_optimized(
                    all_events,
                    eventlog=eventlog,
                    strict=self._strict,
                    max_trait_delta=self._max_trait_delta,
                    on_warn=on_warn,
                )

                # Check if we should create a new snapshot
                should_snap, target_id = should_create_snapshot(eventlog)
                if should_snap:
                    try:
                        create_snapshot(eventlog, target_id)
                        logger.info(f"Created snapshot at event {target_id}")
                    except Exception as e:
                        logger.warning(f"Failed to create snapshot: {e}")
            else:
                self._cached_model = build_self_model(
                    all_events,
                    strict=self._strict,
                    max_trait_delta=self._max_trait_delta,
                    on_warn=on_warn,
                )
            self._last_id = all_events[-1]["id"] if all_events else 0
            self._events_processed = len(all_events)
            return copy.deepcopy(self._cached_model)

        # Incremental update - apply only new events
        logger.debug(
            f"ProjectionCache: Incremental update with {len(new_events)} new events (last_id={self._last_id})"
        )

        self._apply_events_incremental(new_events, on_warn=on_warn)
        self._last_id = new_events[-1]["id"]
        self._events_processed += len(new_events)

        # Periodic verification (check if we just crossed a verification boundary)
        if self._verify_every > 0:
            # Check if we crossed a verification boundary
            prev_checkpoint = (
                self._events_processed - len(new_events)
            ) // self._verify_every
            curr_checkpoint = self._events_processed // self._verify_every
            if curr_checkpoint > prev_checkpoint:
                self._verify_against_full_rebuild(eventlog, on_warn=on_warn)

        return copy.deepcopy(self._cached_model)

    def get_identity(
        self, eventlog, *, on_warn: Callable[[dict], None] | None = None
    ) -> dict:
        """Get cached identity only (faster than full model).

        Returns
        -------
        dict
            Identity with name and traits.
        """
        model = self.get_model(eventlog, on_warn=on_warn)
        return model.get("identity", {})

    def _initialize_empty_model(self) -> dict:
        """Initialize empty model for empty database."""
        return {
            "identity": {
                "name": None,
                "traits": {
                    "openness": 0.5,
                    "conscientiousness": 0.5,
                    "extraversion": 0.5,
                    "agreeableness": 0.5,
                    "neuroticism": 0.5,
                },
            },
            "commitments": {"open": {}, "expired": {}},
        }

    def _apply_events_incremental(
        self, events: list[dict], *, on_warn: Callable[[dict], None] | None = None
    ) -> None:
        """Apply new events to cached model incrementally.

        This replicates the logic from build_self_model() but operates on
        the cached state instead of rebuilding from scratch.
        """
        from pmm.utils.parsers import extract_name_from_change_event

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

        for ev in events:
            kind = ev.get("kind")
            content = ev.get("content", "")
            meta = ev.get("meta") or {}

            try:
                self._last_eid = int(ev.get("id") or 0)
            except Exception:
                self._last_eid = 0

            if kind == "identity_change":
                new_name = meta.get("name")
                if not new_name:
                    # Use deterministic parser
                    new_name = extract_name_from_change_event(content or "")
                if new_name:
                    self._cached_model["identity"]["name"] = new_name

            elif kind == "identity_adopt":
                new_name = meta.get("name") or content or None
                if isinstance(new_name, str):
                    nm = new_name.strip()
                    self._cached_model["identity"]["name"] = nm or None
                    if nm:
                        self._identity_adopted = True

            elif kind == "identity_clear":
                self._cached_model["identity"]["name"] = None
                self._identity_adopted = False

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
                        if self._strict and abs(delta_f) > self._max_trait_delta:
                            delta_f = (
                                self._max_trait_delta
                                if delta_f > 0
                                else -self._max_trait_delta
                            )
                        cur = float(
                            self._cached_model["identity"]["traits"].get(tkey, 0.5)
                        )
                        newv = max(0.0, min(1.0, cur + delta_f))
                        self._cached_model["identity"]["traits"][tkey] = newv
                else:
                    # Single-trait legacy schema
                    try:
                        delta_f = float(delta_field)
                    except Exception:
                        delta_f = 0.0
                    if self._strict and abs(delta_f) > self._max_trait_delta:
                        delta_f = (
                            self._max_trait_delta
                            if delta_f > 0
                            else -self._max_trait_delta
                        )
                    tkey = key_map.get(trait)
                    if tkey:
                        cur = float(
                            self._cached_model["identity"]["traits"].get(tkey, 0.5)
                        )
                        newv = max(0.0, min(1.0, cur + delta_f))
                        self._cached_model["identity"]["traits"][tkey] = newv

            elif kind == "commitment_open":
                cid = meta.get("cid")
                text = meta.get("text")
                if cid and text is not None:
                    entry = {k: v for k, v in meta.items()}
                    self._cached_model["commitments"]["open"][cid] = entry

            elif kind == "evidence_candidate":
                cid = meta.get("cid")
                et = (meta.get("evidence_type") or "done").strip().lower()
                if cid:
                    self._evidence_seen.add((cid, et))

            elif kind in ("commitment_close", "commitment_expire"):
                cid = meta.get("cid")
                if cid and cid in self._cached_model["commitments"]["open"]:
                    if kind == "commitment_close":
                        # Strict ordering: require evidence first
                        if (cid, "done") not in self._evidence_seen:
                            if self._strict:
                                raise ProjectionInvariantError(
                                    f"commitment_close without prior "
                                    f"evidence_candidate (cid={cid}, "
                                    f"eid={self._last_eid})"
                                )
                            # Non-strict: proceed with close but emit warning
                            if callable(on_warn):
                                try:
                                    on_warn(
                                        {
                                            "kind": "projection_warn",
                                            "content": "commitment_close without evidence",
                                            "meta": {
                                                "cid": cid,
                                                "eid": self._last_eid,
                                                "reason": "close_without_evidence",
                                            },
                                        }
                                    )
                                except Exception:
                                    pass

                    # If expire, record in expired section
                    if kind == "commitment_expire":
                        self._cached_model["commitments"]["expired"][cid] = {
                            "text": self._cached_model["commitments"]["open"][cid].get(
                                "text"
                            ),
                            "expired_at": int(ev.get("id") or 0),
                            "reason": (meta or {}).get("reason") or "timeout",
                        }

                    self._cached_model["commitments"]["open"].pop(cid, None)

            elif kind == "commitment_snooze":
                cid = meta.get("cid")
                if cid and cid in self._cached_model["commitments"]["open"]:
                    try:
                        until_t = int(meta.get("until_tick") or 0)
                    except Exception:
                        until_t = 0
                    self._cached_model["commitments"]["open"][cid][
                        "snoozed_until"
                    ] = until_t

        # Final identity invariant check (strict mode)
        if (
            self._strict
            and self._identity_adopted
            and (self._cached_model["identity"].get("name") is None)
        ):
            raise ProjectionInvariantError(
                f"identity reverted to None without identity_clear (last_eid={self._last_eid})"
            )

    def _verify_against_full_rebuild(
        self, eventlog, *, on_warn: Callable[[dict], None] | None = None
    ) -> None:
        """Verify cached model matches full rebuild.

        This is expensive but catches cache divergence bugs.
        """
        logger.debug(
            f"ProjectionCache: Verifying cache at {self._events_processed} events"
        )

        all_events = eventlog.read_all()
        full_model = build_self_model(
            all_events,
            strict=self._strict,
            max_trait_delta=self._max_trait_delta,
            on_warn=on_warn,
        )

        if self._cached_model != full_model:
            self._verifications_failed += 1
            logger.error(
                f"ProjectionCache: Cache diverged from full rebuild at {self._events_processed} events!"
            )
            logger.error(f"Cached: {self._cached_model}")
            logger.error(f"Full: {full_model}")
            raise RuntimeError(
                "ProjectionCache diverged from full rebuild - this is a bug!"
            )

        self._verifications_passed += 1
        logger.debug("ProjectionCache: Verification passed")

    def clear(self) -> None:
        """Clear the cache. Useful for testing or memory management."""
        self._last_id = 0
        self._cached_model = None
        self._evidence_seen.clear()
        self._identity_adopted = False
        self._last_eid = 0
        self._events_processed = 0
        logger.debug("ProjectionCache cleared")

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics for monitoring.

        Returns
        -------
        dict
            Statistics including hits, misses, verifications, etc.
        """
        total = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total if total > 0 else 0.0

        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": hit_rate,
            "events_processed": self._events_processed,
            "last_id": self._last_id,
            "verifications_passed": self._verifications_passed,
            "verifications_failed": self._verifications_failed,
            "cached": self._cached_model is not None,
        }
