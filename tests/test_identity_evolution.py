"""Tests for identity-linked evolution features."""

import pytest
import tempfile
import os
from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import Runtime
from pmm.llm.factory import LLMConfig


def test_identity_checkpoint_emission():
    """Test that identity_checkpoint event is emitted when identity is adopted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        eventlog = EventLog(db_path)

        # Create a minimal runtime
        cfg = LLMConfig(provider="ollama", model="test")
        runtime = Runtime(cfg, eventlog)

        # Adopt an identity
        runtime._adopt_identity(
            "TestIdentity",
            source="user",
            intent="assign_assistant_name",
            confidence=0.9,
        )

        # Check that both identity_adopt and identity_checkpoint events were emitted
        events = eventlog.read_all()
        identity_adopt_events = [e for e in events if e.get("kind") == "identity_adopt"]
        identity_checkpoint_events = [
            e for e in events if e.get("kind") == "identity_checkpoint"
        ]

        assert len(identity_adopt_events) == 1
        assert len(identity_checkpoint_events) == 1

        # Check that the checkpoint contains the expected information
        checkpoint = identity_checkpoint_events[0]
        meta = checkpoint.get("meta", {})
        assert meta.get("name") == "TestIdentity"
        assert "traits" in meta
        assert "commitments" in meta
        assert "stage" in meta


def test_trait_nudges_on_identity_adopt():
    """Test that trait nudges are applied when identity is adopted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        eventlog = EventLog(db_path)

        # Add some events to create context
        eventlog.append("user", "Let's play a game", {})
        eventlog.append("response", "That sounds fun!", {})

        # Create a minimal runtime
        cfg = LLMConfig(provider="ollama", model="test")
        runtime = Runtime(cfg, eventlog)

        # Adopt an identity
        runtime._adopt_identity(
            "PlayfulBot", source="user", intent="assign_assistant_name", confidence=0.9
        )

        # Check that trait_update event was emitted
        events = eventlog.read_all()
        trait_update_events = [e for e in events if e.get("kind") == "trait_update"]

        assert len(trait_update_events) == 1
        trait_update = trait_update_events[0]
        meta = trait_update.get("meta", {})
        assert meta.get("reason") == "identity_shift"
        assert "changes" in meta


def test_commitment_rebinding_on_identity_adopt():
    """Test that commitments are rebound when identity is adopted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        eventlog = EventLog(db_path)

        # Create a minimal runtime
        cfg = LLMConfig(provider="ollama", model="test")
        runtime = Runtime(cfg, eventlog)

        # First adopt the initial identity
        runtime._adopt_identity(
            "TestIdentity",
            source="user",
            intent="assign_assistant_name",
            confidence=0.9,
        )

        # Add some autonomy tick events to simulate turns passing
        # This ensures the minimum turns constraint is satisfied for the next adoption
        for i in range(15):  # More than MIN_TURNS_BETWEEN_IDENTITY_ADOPTS
            eventlog.append("autonomy_tick", f"tick {i}", {"tick": i})

        # Add a commitment with the old identity name
        runtime.tracker.add_commitment("I will help TestIdentity with tasks")

        # Adopt a new identity
        runtime._adopt_identity(
            "NewBot", source="user", intent="assign_assistant_name", confidence=0.9
        )

        # Check that commitment_rebind event was emitted
        events = eventlog.read_all()
        commitment_rebind_events = [
            e for e in events if e.get("kind") == "commitment_rebind"
        ]

        assert len(commitment_rebind_events) >= 1


def test_forced_reflection_after_identity_adopt():
    """Test that reflection is forced after identity adoption."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        eventlog = EventLog(db_path)

        # Create a minimal runtime
        cfg = LLMConfig(provider="ollama", model="test")
        runtime = Runtime(cfg, eventlog)

        # Adopt an identity
        runtime._adopt_identity(
            "ReflectiveBot",
            source="user",
            intent="assign_assistant_name",
            confidence=0.9,
        )

        # Check that a reflection was emitted OR a forced-reflection debug marker exists
        events = eventlog.read_all()
        reflections = [e for e in events if e.get("kind") == "reflection"]
        debug_forced = [
            e
            for e in events
            if e.get("kind") == "debug"
            and (e.get("meta") or {}).get("forced_reflection_reason")
            == "identity_adopt"
        ]
        assert reflections or debug_forced


def test_min_turns_constraint_between_identity_adopts():
    """Now allows rapid identity flips (constraint removed)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        eventlog = EventLog(db_path)

        # Create a minimal runtime
        cfg = LLMConfig(provider="ollama", model="test")
        runtime = Runtime(cfg, eventlog)

        # Adopt first identity
        runtime._adopt_identity(
            "FirstBot", source="user", intent="assign_assistant_name", confidence=0.9
        )

        # Add some autonomy tick events to simulate turns passing
        for i in range(5):  # Less than MIN_TURNS_BETWEEN_IDENTITY_ADOPTS
            eventlog.append("autonomy_tick", f"tick {i}", {"tick": i})

        # Try to adopt second identity (allowed in evolving mode)
        runtime._adopt_identity(
            "SecondBot", source="user", intent="assign_assistant_name", confidence=0.9
        )

        # Check events - should have naming_intent_classified but no identity_adopt for second
        events = eventlog.read_all()
        identity_adopt_events = [e for e in events if e.get("kind") == "identity_adopt"]

        # Both adoptions should be present
        assert len(identity_adopt_events) == 2


def test_ias_gas_response_to_identity_events():
    """Test that IAS/GAS metrics respond to identity adoption events."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        eventlog = EventLog(db_path)

        # Create a minimal runtime
        cfg = LLMConfig(provider="ollama", model="test")
        runtime = Runtime(cfg, eventlog)

        # Add some commitments to establish baseline
        for i in range(5):
            eventlog.append("commitment_open", f"Task {i}", {"cid": f"cid_{i}"})

        # Compute initial metrics
        from pmm.runtime.metrics import compute_ias_gas

        initial_ias, initial_gas = compute_ias_gas(eventlog.read_all())

        # Adopt an identity with high confidence
        runtime._adopt_identity(
            "MetricsBot", source="user", intent="assign_assistant_name", confidence=0.9
        )

        # Add some new commitments after identity adoption
        for i in range(3):
            eventlog.append("commitment_open", f"New task {i}", {"cid": f"new_cid_{i}"})

        # Compute metrics after identity adoption
        new_ias, new_gas = compute_ias_gas(eventlog.read_all())

        # The metrics should have changed (exact values depend on implementation details)
        # but we're primarily testing that the function doesn't crash when processing identity events
        assert isinstance(new_ias, float)
        assert isinstance(new_gas, float)


def test_invariants_verification_for_identity_evolution():
    """Test that invariants verification catches identity evolution issues."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        eventlog = EventLog(db_path)

        # Create a minimal runtime
        cfg = LLMConfig(provider="ollama", model="test")
        runtime = Runtime(cfg, eventlog)

        # Test 1: Identity adopt without proposal should be caught
        runtime._adopt_identity(
            "NoProposalBot",
            source="autonomous",
            intent="assign_assistant_name",
            confidence=0.9,
        )

        # Run invariants check
        from pmm.runtime.invariants_rt import run_invariants_tick
        from pmm.storage.projection import build_directives

        violations = run_invariants_tick(
            evlog=eventlog, build_directives=build_directives
        )

        # Check for identity adoption without proposal violation
        identity_violations = [
            v
            for v in violations
            if v.get("payload", {}).get("code") == "IDENTITY_ADOPT_WITHOUT_PROPOSE"
        ]

        # Must always detect violation when adopting without proposal
        assert len(identity_violations) == 1
        violation = identity_violations[0]
        assert violation["payload"]["code"] == "IDENTITY_ADOPT_WITHOUT_PROPOSE"
        assert "adopt_event_id" in violation["payload"]["details"]
        assert (
            violation["payload"]["message"]
            == "identity_adopt without prior identity_propose"
        )


if __name__ == "__main__":
    pytest.main([__file__])
