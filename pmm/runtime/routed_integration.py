"""Integration layer for routed context system.

Provides feature flag and integration utilities to gradually migrate
from tail-constrained reads to full-history routing.

Feature flag: PMM_ROUTED_CONTEXT (default: on)
- on: Use EventRouter + IdentityResolver (full history access)
- off: Use original tail-constrained reads (fallback)
"""

import os
from typing import Any

from pmm.runtime.event_router import EventRouter
from pmm.runtime.identity_resolver import IdentityResolver
from pmm.runtime.routed_context_builder import build_context_with_router
from pmm.runtime.snapshot import LedgerSnapshot
from pmm.storage.event_index import EventIndex
from pmm.storage.eventlog import EventLog

__all__ = [
    "is_routed_context_enabled",
    "create_routed_infrastructure",
    "build_context_routed_or_fallback",
]


def is_routed_context_enabled() -> bool:
    """Check if routed context is enabled via feature flag.

    Returns:
        True if PMM_ROUTED_CONTEXT is 'on' (default), False if 'off'
    """
    flag_value = os.environ.get("PMM_ROUTED_CONTEXT", "on").lower()
    return flag_value in ("on", "true", "1", "yes")


def create_routed_infrastructure(
    eventlog: EventLog,
) -> tuple[EventIndex, EventRouter, IdentityResolver]:
    """Create routed infrastructure components.

    Args:
        eventlog: EventLog instance

    Returns:
        Tuple of (EventIndex, EventRouter, IdentityResolver)
    """
    event_index = EventIndex(eventlog)
    event_router = EventRouter(eventlog, event_index)
    identity_resolver = IdentityResolver(eventlog, event_router)

    return event_index, event_router, identity_resolver


def build_context_routed_or_fallback(
    eventlog: EventLog,
    *,
    routed_infrastructure: (
        tuple[EventIndex, EventRouter, IdentityResolver] | None
    ) = None,
    snapshot: LedgerSnapshot | None = None,
    n_reflections: int = 3,
    max_commitment_chars: int = 400,
    max_reflection_chars: int = 600,
    compact_mode: bool = False,
    include_metrics: bool = True,
    include_commitments: bool = True,
    include_reflections: bool = True,
    diagnostics: dict[str, Any] | None = None,
    memegraph=None,  # For fallback compatibility
) -> str:
    """Build context using routed system or fallback to original.

    This function provides a drop-in replacement for the original context builder
    with automatic fallback based on feature flag and infrastructure availability.

    Args:
        eventlog: EventLog instance
        routed_infrastructure: Optional pre-created (EventIndex, EventRouter, IdentityResolver)
        snapshot: Optional snapshot for fallback mode
        n_reflections: Number of reflections to include
        max_commitment_chars: Max chars for commitment block
        max_reflection_chars: Max chars for reflection block
        compact_mode: Whether to use compact format
        include_metrics: Whether to include IAS/GAS/Stage
        include_commitments: Whether to include commitments
        include_reflections: Whether to include reflections
        diagnostics: Optional diagnostics output dict
        memegraph: MemeGraph for fallback compatibility

    Returns:
        Context string with truth-source tagging
    """

    # Initialize diagnostics
    if diagnostics is None:
        diagnostics = {}

    # Check feature flag
    if not is_routed_context_enabled():
        # Fallback to original context builder
        from pmm.runtime.context_builder import build_context_from_ledger

        diagnostics.update(
            {
                "routing_enabled": False,
                "fallback_reason": "feature_flag_disabled",
                "truth_source": "tail_fallback",
            }
        )

        return build_context_from_ledger(
            eventlog=eventlog,
            snapshot=snapshot,
            n_reflections=n_reflections,
            use_tail_optimization=True,  # Use tail optimization in fallback
            memegraph=memegraph,
            max_commitment_chars=max_commitment_chars,
            max_reflection_chars=max_reflection_chars,
            compact_mode=compact_mode,
            include_metrics=include_metrics,
            include_commitments=include_commitments,
            include_reflections=include_reflections,
            diagnostics=diagnostics,
        )

    # Try routed context
    try:
        # Create infrastructure if not provided
        if routed_infrastructure is None:
            event_index, event_router, identity_resolver = create_routed_infrastructure(
                eventlog
            )
        else:
            event_index, event_router, identity_resolver = routed_infrastructure

        # Use routed context builder
        diagnostics.update(
            {
                "routing_enabled": True,
                "fallback_reason": None,
                "infrastructure_created": routed_infrastructure is None,
            }
        )

        return build_context_with_router(
            eventlog=eventlog,
            event_router=event_router,
            snapshot=snapshot,
            n_reflections=n_reflections,
            max_commitment_chars=max_commitment_chars,
            max_reflection_chars=max_reflection_chars,
            compact_mode=compact_mode,
            include_metrics=include_metrics,
            include_commitments=include_commitments,
            include_reflections=include_reflections,
            diagnostics=diagnostics,
        )

    except Exception as e:
        # Fallback to original on any error
        from pmm.runtime.context_builder import build_context_from_ledger

        diagnostics.update(
            {
                "routing_enabled": False,
                "fallback_reason": f"router_error: {str(e)}",
                "truth_source": "tail_fallback",
            }
        )

        return build_context_from_ledger(
            eventlog=eventlog,
            snapshot=snapshot,
            n_reflections=n_reflections,
            use_tail_optimization=True,
            memegraph=memegraph,
            max_commitment_chars=max_commitment_chars,
            max_reflection_chars=max_reflection_chars,
            compact_mode=compact_mode,
            include_metrics=include_metrics,
            include_commitments=include_commitments,
            include_reflections=include_reflections,
            diagnostics=diagnostics,
        )


class RoutedContextManager:
    """Context manager for routed infrastructure with caching.

    Provides efficient reuse of routed infrastructure components
    across multiple context building operations.
    """

    def __init__(self, eventlog: EventLog):
        self.eventlog = eventlog
        self._infrastructure: (
            tuple[EventIndex, EventRouter, IdentityResolver] | None
        ) = None
        self._enabled = is_routed_context_enabled()

    def get_infrastructure(
        self,
    ) -> tuple[EventIndex, EventRouter, IdentityResolver] | None:
        """Get cached infrastructure or create if needed."""
        if not self._enabled:
            return None

        if self._infrastructure is None:
            self._infrastructure = create_routed_infrastructure(self.eventlog)

        return self._infrastructure

    def build_context(self, **kwargs) -> str:
        """Build context using cached infrastructure."""
        infrastructure = self.get_infrastructure()

        return build_context_routed_or_fallback(
            eventlog=self.eventlog, routed_infrastructure=infrastructure, **kwargs
        )

    def get_identity_resolver(self) -> IdentityResolver | None:
        """Get identity resolver if routed context is enabled."""
        infrastructure = self.get_infrastructure()
        return infrastructure[2] if infrastructure else None

    def get_stats(self) -> dict[str, Any]:
        """Get infrastructure statistics."""
        if not self._enabled:
            return {"routing_enabled": False}

        infrastructure = self.get_infrastructure()
        if not infrastructure:
            return {"routing_enabled": False, "infrastructure_available": False}

        event_index, event_router, identity_resolver = infrastructure

        return {
            "routing_enabled": True,
            "infrastructure_available": True,
            "event_index_stats": event_index.get_stats(),
            "event_router_stats": event_router.get_stats(),
            "identity_resolver_stats": identity_resolver.get_stats(),
        }
