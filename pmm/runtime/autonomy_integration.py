"""Autonomous PMM Integration Module

Integrates all autonomous systems into the runtime loop:
- TraitDriftManager for personality evolution
- StageBehaviorManager for stage-aware adaptations
- EmergenceManager for multi-dimensional behavioral analysis
- AdaptiveReflectionCadence for intelligent reflection timing
- ProactiveCommitmentManager for commitment health monitoring

All systems follow CONTRIBUTING.md principles:
- Deterministic, auditable behavior
- Idempotent event emissions
- No brittle keyword triggers
- Event-driven architecture
"""

from __future__ import annotations

import time

from pmm.commitments.manager import ProactiveCommitmentManager
from pmm.personality.self_evolution import TraitDriftManager

# IntrospectionEngine removed - functionality integrated into emergence system
from pmm.runtime.adaptive_cadence import AdaptiveReflectionCadence
from pmm.runtime.snapshot import LedgerSnapshot
from pmm.runtime.stage_behaviors import StageBehaviorManager
from pmm.runtime.stage_tracker import StageTracker
from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model


class AutonomousSystemsManager:
    """Manages all autonomous PMM systems with coordinated event processing."""

    def __init__(self, eventlog: EventLog):
        self.eventlog = eventlog

        # Initialize all autonomous systems
        self.trait_drift = TraitDriftManager()
        self.stage_behavior = StageBehaviorManager()
        # IntrospectionEngine replaced by EmergenceManager
        from pmm.runtime.emergence import EmergenceManager

        self.emergence = EmergenceManager(eventlog)
        self.reflection_cadence = AdaptiveReflectionCadence()
        self.commitment_manager = ProactiveCommitmentManager()

    def process_autonomy_tick(
        self,
        tick_id: str,
        context: dict,
        snapshot: LedgerSnapshot | None = None,
    ) -> dict:
        """Process a single autonomy tick through all systems.

        Args:
            tick_id: Unique identifier for this tick
            context: Contextual information including stage, confidence, etc.

        Returns:
            Dict with processing results and recommendations
        """
        if snapshot is not None:
            events = snapshot.events
        else:
            events = self.eventlog.read_all()
        results = {
            "tick_id": tick_id,
            "timestamp": time.time(),
            "systems_processed": [],
            "events_emitted": 0,
            "recommendations": [],
        }

        # Track events before processing
        events_before = len(events)

        # 1. Process trait drift for recent events
        try:
            recent_events = events[-50:] if len(events) > 50 else events
            for event in recent_events:
                if event.get("kind") in [
                    "user_message",
                    "reflection",
                    "commitment_open",
                    "commitment_close",
                ]:
                    self.trait_drift.apply_and_log(self.eventlog, event, context)
            results["systems_processed"].append("trait_drift")
        except Exception as e:
            results["errors"] = results.get("errors", [])
            results["errors"].append(f"trait_drift: {str(e)}")

        # 2. Update stage behaviors if stage changed
        try:
            current_stage = context.get("stage", "S0")
            confidence = context.get("confidence", 0.5)
            self.stage_behavior.maybe_emit_stage_policy_update(
                self.eventlog, current_stage, confidence, tick_id
            )
            results["systems_processed"].append("stage_behavior")
        except Exception as e:
            results["errors"] = results.get("errors", [])
            results["errors"].append(f"stage_behavior: {str(e)}")

        # 3. Run emergence analysis (replaces introspection)
        try:
            window_events = events[-100:] if len(events) > 100 else events
            self.emergence.emit_emergence_report(window_events)
            results["systems_processed"].append("emergence")
        except Exception as e:
            results["errors"] = results.get("errors", [])
            results["errors"].append(f"emergence: {str(e)}")

        # 4. Evaluate reflection cadence
        try:
            should_reflect = self.reflection_cadence.should_reflect(
                self.eventlog, tick_id, context
            )
            self.reflection_cadence.maybe_emit_decision(
                self.eventlog, tick_id, should_reflect, context
            )
            if should_reflect:
                results["recommendations"].append(
                    {
                        "type": "reflection",
                        "reason": "adaptive_cadence_triggered",
                        "priority": "high",
                    }
                )
            results["systems_processed"].append("reflection_cadence")
        except Exception as e:
            results["errors"] = results.get("errors", [])
            results["errors"].append(f"reflection_cadence: {str(e)}")

        # 5. Assess commitment health
        try:
            commitment_events = [
                e for e in events if e.get("kind", "").startswith("commitment_")
            ]
            self.commitment_manager.maybe_emit_health_report(
                self.eventlog, commitment_events
            )

            # Generate recommendations based on health
            health = self.commitment_manager.evaluate_commitment_health(
                commitment_events
            )
            adjustments = self.commitment_manager.suggest_commitment_adjustments(health)
            for adj in adjustments:
                results["recommendations"].append(
                    {
                        "type": "commitment_adjustment",
                        "action": adj["action"],
                        "reason": adj["reason"],
                        "priority": "medium",
                    }
                )
            results["systems_processed"].append("commitment_manager")
        except Exception as e:
            results["errors"] = results.get("errors", [])
            results["errors"].append(f"commitment_manager: {str(e)}")

        # Count new events emitted
        events_after = len(self.eventlog.read_all())
        results["events_emitted"] = events_after - events_before

        return results

    def get_system_status(self, snapshot: LedgerSnapshot | None = None) -> dict:
        """Get status of all autonomous systems."""
        if snapshot is not None:
            events = snapshot.events
        else:
            events = self.eventlog.read_all()

        # Get current stage and model
        current_stage, stage_snapshot = StageTracker.infer_stage(events)
        model = build_self_model(events, eventlog=self.eventlog)

        return {
            "current_stage": current_stage,
            "stage_confidence": stage_snapshot.get("confidence", 0.0),
            "total_events": len(events),
            "systems": {
                "trait_drift": {
                    "active": True,
                    "last_policy_update": self._find_last_event(
                        events, "policy_update", "trait_drift"
                    ),
                },
                "stage_behavior": {
                    "active": True,
                    "current_stage": current_stage,
                    "last_policy_update": self._find_last_event(
                        events, "policy_update", "stage_behavior"
                    ),
                },
                "emergence": {
                    "active": True,
                    "last_report": self._find_last_event(events, "emergence_report"),
                },
                "reflection_cadence": {
                    "active": True,
                    "last_decision": self._find_last_event(
                        events, "reflection_decision"
                    ),
                },
                "commitment_manager": {
                    "active": True,
                    "last_health_report": self._find_last_event(
                        events, "commitment_health"
                    ),
                    "open_commitments": len(
                        model.get("commitments", {}).get("open", {})
                    ),
                },
            },
        }

    def _find_last_event(
        self, events: list[dict], kind: str, component: str = None
    ) -> dict | None:
        """Find the most recent event of a given kind and optional component."""
        for event in reversed(events):
            if event.get("kind") == kind:
                if component is None:
                    return {"id": event.get("id"), "timestamp": event.get("timestamp")}
                meta = event.get("meta", {})
                if meta.get("component") == component:
                    return {"id": event.get("id"), "timestamp": event.get("timestamp")}
        return None


def integrate_autonomous_systems_into_tick(
    eventlog: EventLog,
    tick_id: str,
    stage: str,
    confidence: float,
    ias: float,
    gas: float,
) -> dict:
    """Integration function to be called from AutonomyLoop.tick().

    This function processes all autonomous systems during an autonomy tick
    and returns results for logging and decision making.

    Args:
        eventlog: The event log instance
        tick_id: Unique identifier for this tick
        stage: Current PMM stage (S0-S4)
        confidence: Stage confidence level (0.0-1.0)
        ias: Current IAS metric
        gas: Current GAS metric

    Returns:
        Dict with processing results and recommendations
    """
    manager = AutonomousSystemsManager(eventlog)

    context = {
        "stage": stage,
        "confidence": confidence,
        "ias": ias,
        "gas": gas,
        "tick_id": tick_id,
    }

    return manager.process_autonomy_tick(tick_id, context)


def validate_autonomous_event_emissions(eventlog: EventLog) -> dict:
    """Validate that all autonomous systems emit events according to CONTRIBUTING.md.

    Checks:
    - Events are deterministic and idempotent
    - Metadata is complete and consistent
    - No duplicate events for same conditions
    - Event structure follows PMM conventions

    Returns:
        Dict with validation results
    """
    events = eventlog.read_all()
    results = {
        "total_events": len(events),
        "autonomous_events": 0,
        "validation_errors": [],
        "validation_warnings": [],
        "systems_validated": [],
    }

    # Track autonomous event types
    autonomous_kinds = {
        "policy_update",
        "emergence_report",
        "reflection_decision",
        "commitment_health",
        "trait_update",
    }

    # Validate each autonomous event
    for event in events:
        kind = event.get("kind", "")
        if kind not in autonomous_kinds:
            continue

        results["autonomous_events"] += 1

        # Check required fields - EventLog automatically adds timestamp, so skip that check
        if not event.get("id"):
            results["validation_errors"].append(f"Event {kind} missing id")

        # Check metadata completeness
        meta = event.get("meta", {})
        if not meta.get("component"):
            results["validation_warnings"].append(
                f"Event {kind} missing component in metadata"
            )
        if "deterministic" not in meta:
            results["validation_warnings"].append(
                f"Event {kind} missing deterministic flag"
            )

        # Check for proper digest/idempotency keys where expected
        if kind in ["emergence_report", "commitment_health"]:
            if not meta.get("digest"):
                results["validation_errors"].append(
                    f"Event {kind} missing digest for idempotency"
                )

    # Check for duplicate events (basic idempotency validation)
    event_signatures = {}
    for event in events:
        kind = event.get("kind", "")
        if kind not in autonomous_kinds:
            continue

        meta = event.get("meta", {})
        component = meta.get("component", "")

        # Create signature for idempotency check
        if kind == "policy_update":
            sig = f"{kind}:{component}:{meta.get('stage')}:{str(meta.get('params'))}"
        elif kind == "emergence_report":
            sig = f"{kind}:{component}:{meta.get('digest')}"
        elif kind == "reflection_decision":
            sig = f"{kind}:{component}:{meta.get('tick_id')}"
        elif kind == "commitment_health":
            sig = f"{kind}:{component}:{meta.get('digest')}"
        else:
            sig = f"{kind}:{component}:{event.get('id')}"

        if sig in event_signatures:
            results["validation_errors"].append(f"Duplicate event signature: {sig}")
        else:
            event_signatures[sig] = event.get("id")

    results["systems_validated"] = list(autonomous_kinds)
    results["unique_signatures"] = len(event_signatures)

    return results
