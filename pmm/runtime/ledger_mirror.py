"""Request-scoped cached view over the ledger for mirror-first reads."""

from __future__ import annotations

import threading
from typing import Any

from pmm.runtime.memegraph import MemeGraphProjection
from pmm.runtime.stage_tracker import StageTracker
from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_identity, build_self_model


class LedgerMirror:
    """Lightweight read-through cache that leans on memegraph indices first."""

    _global_cache: dict[str, Any] = {}
    _global_lock = threading.RLock()

    def __init__(self, eventlog: EventLog, memegraph: MemeGraphProjection) -> None:
        self.eventlog = eventlog
        self.memegraph = memegraph
        path = getattr(eventlog, "path", None)
        if path is None:
            path = repr(eventlog)
        self._cache_prefix = f"{path}:{id(eventlog)}"

    # ------------------------------------------------------------------ utils

    def _get(self, key: str, loader) -> Any:
        with self.__class__._global_lock:
            namespaced = f"{self._cache_prefix}:{key}"
            if namespaced not in self.__class__._global_cache:
                self.__class__._global_cache[namespaced] = loader()
            return self.__class__._global_cache[namespaced]

    @classmethod
    def invalidate(cls) -> None:
        """Clear the global cache to force fresh reads from disk."""
        with cls._global_lock:
            cls._global_cache.clear()

    @classmethod
    def sync(cls, force: bool = False) -> None:
        """Sync the mirror, optionally forcing a reload from disk."""
        if force:
            cls.invalidate()

    # ------------------------------------------------------------- raw reads

    def read_by_ids(
        self, ids: list[int], verify_hash: bool | None = None
    ) -> list[dict]:
        ids_clean = [int(i) for i in ids if isinstance(i, int)]
        if not ids_clean:
            return []
        ids_sorted = tuple(sorted(ids_clean))

        def _load() -> list[dict]:
            kwargs = {} if verify_hash is None else {"verify_hash": verify_hash}
            return self.eventlog.read_by_ids(list(ids_sorted), **kwargs)

        return self._get(f"ids:{ids_sorted}:{verify_hash}", _load)

    def read_tail(self, limit: int = 1000) -> list[dict]:
        key = f"tail:{limit}"

        def _load() -> list[dict]:
            try:
                ids = sorted(self.memegraph.event_ids(), reverse=True)[: int(limit)]
                if ids:
                    return self.eventlog.read_by_ids(ids)
            except Exception:
                pass
            return self.eventlog.read_tail(limit=limit)

        return self._get(key, _load)

    def read_all(self) -> list[dict]:
        def _load() -> list[dict]:
            try:
                ids = self.memegraph.event_ids()
                if ids:
                    return self.eventlog.read_by_ids(ids)
            except Exception:
                pass
            return self.eventlog.read_all()

        return self._get("all", _load)

    # --------------------------------------------------------- derived views

    def get_identity(self) -> dict[str, Any]:
        def _load() -> dict[str, Any]:
            events = self.read_tail(limit=5000)
            return build_identity(events)

        return self._get("identity", _load)

    def get_open_commitment_events(self, max_events: int = 10) -> list[dict]:
        key = f"open_commitments:{max_events}"

        def _load() -> list[dict]:
            ids: list[int] = []
            snapshot = None
            try:
                snapshot = self.memegraph.open_commitments_snapshot()
            except Exception:
                snapshot = None

            if snapshot:
                try:
                    for data in snapshot.values():
                        eid = data.get("last_event_id")
                        if isinstance(eid, int) and eid > 0:
                            ids.append(int(eid))
                except Exception:
                    ids = []

            if not ids:
                try:
                    for row in self.eventlog.get_open_commitments(limit=max_events):
                        eid = int(row.get("id", 0))
                        if eid > 0:
                            ids.append(eid)
                except Exception:
                    ids = []

            if not ids:
                return []

            try:
                events = self.read_by_ids(sorted(set(ids)))
            except Exception:
                events = []

            if snapshot:
                open_cids = {str(cid) for cid in snapshot.keys()}
                events = [
                    ev
                    for ev in events
                    if (ev.get("meta") or {}).get("cid") in open_cids
                ]

            events.sort(key=lambda ev: int(ev.get("id") or 0))
            return events[: int(max_events)]

        return self._get(key, _load)

    def get_open_commitment_projection(self) -> dict[str, Any]:
        def _load() -> dict[str, Any]:
            try:
                return self.memegraph.open_commitments_snapshot()
            except Exception:
                return {}

        return self._get("open_commitments_snapshot", _load)

    def infer_stage(self) -> str | None:
        def _load() -> str | None:
            events = self.read_tail(limit=1000)
            try:
                stage, _ = StageTracker.infer_stage(events)
                return stage
            except Exception:
                return None

        return self._get("stage", _load)

    def get_self_model(self) -> dict[str, Any]:
        def _load() -> dict[str, Any]:
            events = self.read_tail(limit=5000)
            return build_self_model(events, eventlog=self.eventlog)

        return self._get("self_model", _load)
