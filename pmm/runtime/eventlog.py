"""Runtime-facing EventLog wrapper.

This module re-exports the structured EventLog implementation used throughout
PMM. Runtime code should import EventLog from here so we can evolve runtime-
level behavior without reaching into storage internals.
"""

from __future__ import annotations

from pmm.storage.eventlog import EventLog as _StorageEventLog


class EventLog(_StorageEventLog):
    """Structured ledger abstraction for runtime code.

    This subclass exists as a stable import location for runtime modules. It
    currently delegates to the storage-layer implementation while giving us a
    hook to extend runtime-specific helpers (e.g., request-scoped listeners or
    structured append wrappers) without editing storage internals.
    """

    __slots__ = ()

    def count_events(self, kind: str) -> int:
        """Return count of events of a given kind.

        Uses SQL count when available and falls back to projection if needed, to
        preserve deterministic ledger reads.
        """

        try:
            with self._lock:  # type: ignore[attr-defined]
                row = self._conn.execute(  # type: ignore[attr-defined]
                    "SELECT COUNT(*) FROM events WHERE kind=?",
                    (str(kind),),
                ).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            try:
                return sum(
                    1 for event in self.read_all() if event.get("kind") == str(kind)
                )
            except Exception:
                return 0
