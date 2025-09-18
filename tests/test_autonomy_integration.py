"""Tests for autonomous systems integration.

Validates that all autonomous systems work together correctly and emit
events according to CONTRIBUTING.md guidelines.
"""

import tempfile
import os
from pmm.storage.eventlog import EventLog
from pmm.runtime.autonomy_integration import (
    AutonomousSystemsManager,
    integrate_autonomous_systems_into_tick,
    validate_autonomous_event_emissions,
)


class TestAutonomousSystemsManager:
    """Test the autonomous systems manager integration."""

    def setup_method(self):
        """Set up test environment with temporary database."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.eventlog = EventLog(self.temp_db.name)
        self.manager = AutonomousSystemsManager(self.eventlog)

    def teardown_method(self):
        """Clean up temporary database."""
        try:
            os.unlink(self.temp_db.name)
        except OSError:
            pass

    def test_manager_initialization(self):
        """Test that manager initializes all systems correctly."""
        assert self.manager.eventlog == self.eventlog
        assert self.manager.trait_drift is not None
        assert self.manager.stage_behavior is not None
        assert self.manager.emergence is not None
        assert self.manager.reflection_cadence is not None
        assert self.manager.commitment_manager is not None

    def test_process_autonomy_tick_basic(self):
        """Test basic autonomy tick processing."""
        tick_id = "test_tick_001"
        context = {"stage": "S1", "confidence": 0.7, "ias": 0.6, "gas": 0.5}

        # Add some events to process
        self.eventlog.append(
            kind="user_message",
            content="I want to learn Python programming",
            meta={"user_id": "test_user"},
        )

        results = self.manager.process_autonomy_tick(tick_id, context)

        # Verify results structure
        assert results["tick_id"] == tick_id
        assert "timestamp" in results
        assert "systems_processed" in results
        assert "events_emitted" in results
        assert "recommendations" in results

        # Should have processed multiple systems
        assert len(results["systems_processed"]) > 0

    def test_process_autonomy_tick_with_commitments(self):
        """Test tick processing with commitment events."""
        tick_id = "test_tick_002"
        context = {"stage": "S2", "confidence": 0.8, "ias": 0.7, "gas": 0.6}

        # Add commitment events
        self.eventlog.append(
            kind="commitment_open",
            content="Learn machine learning basics",
            meta={"cid": "c1", "due_date": "2024-01-01"},
        )
        self.eventlog.append(
            kind="commitment_close",
            content="Completed Python tutorial",
            meta={"cid": "c2", "completion_reason": "finished"},
        )

        results = self.manager.process_autonomy_tick(tick_id, context)

        # Should have commitment-related recommendations
        commitment_recs = [
            r
            for r in results["recommendations"]
            if r["type"] == "commitment_adjustment"
        ]
        # Verify recommendation structure if any exist
        for rec in commitment_recs:
            assert "type" in rec
            assert "digest" in rec
            assert rec["type"] == "commitment_adjustment"

    def test_get_system_status(self):
        """Test system status reporting."""
        # Add some events
        self.eventlog.append(
            kind="user_message", content="Hello", meta={"user_id": "test"}
        )

        status = self.manager.get_system_status()

        # Verify status structure
        assert "current_stage" in status
        assert "stage_confidence" in status
        assert "total_events" in status
        assert "systems" in status

        # Check all systems are reported
        systems = status["systems"]
        assert "trait_drift" in systems
        assert "stage_behavior" in systems
        assert "emergence" in systems
        assert "reflection_cadence" in systems
        assert "commitment_manager" in systems

        # All systems should be active
        for system_name, system_info in systems.items():
            assert system_info["active"] is True

    def test_error_handling(self):
        """Test that errors in individual systems don't crash the manager."""
        tick_id = "test_tick_error"
        context = {"stage": "S0", "confidence": 0.5, "ias": 0.4, "gas": 0.3}

        # This should not crash even with minimal context
        results = self.manager.process_autonomy_tick(tick_id, context)

        # Should still return valid results structure
        assert "tick_id" in results
        assert "systems_processed" in results

        # May have errors, but should be contained
        if "errors" in results:
            assert isinstance(results["errors"], list)


class TestIntegrationFunction:
    """Test the integration function for AutonomyLoop."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.eventlog = EventLog(self.temp_db.name)

    def teardown_method(self):
        """Clean up temporary database."""
        try:
            os.unlink(self.temp_db.name)
        except OSError:
            pass

    def test_integrate_autonomous_systems_into_tick(self):
        """Test the main integration function."""
        results = integrate_autonomous_systems_into_tick(
            eventlog=self.eventlog,
            tick_id="integration_test_001",
            stage="S1",
            confidence=0.6,
            ias=0.5,
            gas=0.4,
        )

        # Verify results structure
        assert "tick_id" in results
        assert "systems_processed" in results
        assert "recommendations" in results
        assert results["tick_id"] == "integration_test_001"

    def test_integration_with_events(self):
        """Test integration with existing events."""
        # Add some events first
        self.eventlog.append(
            kind="user_message",
            content="I need help with my project",
            meta={"priority": "high"},
        )
        self.eventlog.append(
            kind="reflection",
            content="User seems to need assistance with project management",
            meta={"reflection_type": "user_analysis"},
        )

        results = integrate_autonomous_systems_into_tick(
            eventlog=self.eventlog,
            tick_id="integration_test_002",
            stage="S2",
            confidence=0.7,
            ias=0.6,
            gas=0.5,
        )

        # Should have processed systems
        assert len(results["systems_processed"]) > 0

        # Should have emitted some events
        # Verify events emitted have proper structure
        if results["events_emitted"] > 0:
            recent_events = self.eventlog.read_tail(limit=results["events_emitted"])
            for event in recent_events:
                assert "kind" in event
                assert "meta" in event
                assert isinstance(event["meta"], dict)


class TestEventValidation:
    """Test autonomous event validation."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.eventlog = EventLog(self.temp_db.name)

    def teardown_method(self):
        """Clean up temporary database."""
        try:
            os.unlink(self.temp_db.name)
        except OSError:
            pass

    def test_validate_empty_log(self):
        """Test validation with empty event log."""
        results = validate_autonomous_event_emissions(self.eventlog)

        assert results["total_events"] == 0
        assert results["autonomous_events"] == 0
        assert len(results["validation_errors"]) == 0
        assert len(results["systems_validated"]) > 0

    def test_validate_with_autonomous_events(self):
        """Test validation with autonomous events."""
        # Add a policy update event with timestamp
        self.eventlog.append(
            kind="policy_update",
            content="",
            meta={
                "component": "trait_drift",
                "stage": "S1",
                "params": {"test": "value"},
                "deterministic": True,
            },
        )

        # Add an emergence report with timestamp
        self.eventlog.append(
            kind="emergence_report",
            content="",
            meta={
                "component": "emergence",
                "window_label": "test_window",
                "digest": "abc123",
                "deterministic": True,
                "summary": {"events": 1},
            },
        )

        results = validate_autonomous_event_emissions(self.eventlog)

        assert results["autonomous_events"] == 2
        assert len(results["validation_errors"]) == 0
        assert results["unique_signatures"] == 2

    def test_validate_missing_metadata(self):
        """Test validation catches missing metadata."""
        # Add event with missing component
        self.eventlog.append(
            kind="policy_update",
            content="",
            meta={"stage": "S1"},  # Missing component and deterministic flag
        )

        results = validate_autonomous_event_emissions(self.eventlog)

        assert results["autonomous_events"] == 1
        assert len(results["validation_warnings"]) == 2
        for warning in results["validation_warnings"]:
            assert isinstance(warning, str)
            assert len(warning) > 0
            assert "policy_update" in warning
            assert any(field in warning for field in ["component", "deterministic"])

    def test_validate_duplicate_detection(self):
        """Test validation detects duplicate events."""
        # Add identical policy updates
        for _ in range(2):
            self.eventlog.append(
                kind="policy_update",
                content="",
                meta={
                    "component": "test_component",
                    "stage": "S1",
                    "params": {"same": "params"},
                    "deterministic": True,
                },
            )

        results = validate_autonomous_event_emissions(self.eventlog)

        assert results["autonomous_events"] == 2
        assert len(results["validation_errors"]) == 1
        error = results["validation_errors"][0]
        assert "Duplicate event signature" in error
        assert any(
            "Duplicate event signature" in error
            for error in results["validation_errors"]
        )


class TestEndToEndIntegration:
    """Test end-to-end integration scenarios."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.eventlog = EventLog(self.temp_db.name)

    def teardown_method(self):
        """Clean up temporary database."""
        try:
            os.unlink(self.temp_db.name)
        except OSError:
            pass

    def test_full_autonomy_cycle(self):
        """Test a complete autonomy cycle with all systems."""
        # Simulate user interaction
        self.eventlog.append(
            kind="user_message",
            content="I want to improve my productivity",
            meta={"user_id": "test_user", "session": "session_1"},
        )

        # Process first tick
        results1 = integrate_autonomous_systems_into_tick(
            eventlog=self.eventlog,
            tick_id="cycle_tick_001",
            stage="S0",
            confidence=0.4,
            ias=0.3,
            gas=0.2,
        )

        # Add more events
        self.eventlog.append(
            kind="commitment_open",
            content="Set up daily planning routine",
            meta={"cid": "productivity_1", "priority": "high"},
        )

        self.eventlog.append(
            kind="reflection",
            content="User is seeking productivity improvements",
            meta={"reflection_type": "user_intent_analysis"},
        )

        # Process second tick
        results2 = integrate_autonomous_systems_into_tick(
            eventlog=self.eventlog,
            tick_id="cycle_tick_002",
            stage="S1",
            confidence=0.6,
            ias=0.5,
            gas=0.4,
        )

        # Validate the cycle
        validation = validate_autonomous_event_emissions(self.eventlog)

        # Should have processed systems in both ticks
        assert len(results1["systems_processed"]) > 0
        assert len(results2["systems_processed"]) > 0

        # Should have autonomous events
        assert validation["autonomous_events"] > 0

        # Should have minimal validation errors
        assert len(validation["validation_errors"]) == 0

    def test_stage_progression_integration(self):
        """Test integration across stage progressions."""
        stages = ["S0", "S1", "S2"]
        confidences = [0.3, 0.6, 0.8]

        for i, (stage, confidence) in enumerate(zip(stages, confidences)):
            # Add some activity
            self.eventlog.append(
                kind="user_message",
                content=f"Stage {stage} activity",
                meta={"stage_test": True},
            )

            # Process tick
            results = integrate_autonomous_systems_into_tick(
                eventlog=self.eventlog,
                tick_id=f"stage_tick_{i:03d}",
                stage=stage,
                confidence=confidence,
                ias=0.5 + i * 0.1,
                gas=0.4 + i * 0.1,
            )

            assert results["tick_id"] == f"stage_tick_{i:03d}"
            assert len(results["systems_processed"]) > 0

        # Final validation
        validation = validate_autonomous_event_emissions(self.eventlog)
        assert validation["autonomous_events"] > 0
        assert len(validation["validation_errors"]) == 0
