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
