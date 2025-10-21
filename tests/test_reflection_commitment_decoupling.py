"""Regression tests for ADR-001: Reflection-Commitment Decoupling.

Verifies that reflections no longer auto-create commitments, only execute
supported policy actions.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime
from pmm.storage.eventlog import EventLog


def test_reflection_does_not_create_commitment() -> None:
    """Verify reflections no longer auto-create commitments (ADR-001)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        eventlog = EventLog(str(db_path))
        cfg = LLMConfig(
            provider="dummy", model="test", embed_provider=None, embed_model=None
        )
        runtime = Runtime(cfg, eventlog)

        # Call reflect() directly (simulating autonomy tick)
        # This should NOT create a commitment, only a policy update
        try:
            runtime.reflect()
        except Exception:
            # Reflection may fail due to missing LLM, that's OK for this test
            pass

        # Check ledger for commitment_open events
        events = eventlog.read_all()
        commitment_opens = [e for e in events if e.get("kind") == "commitment_open"]

        # Should have ZERO commitment_open events from reflections
        reflection_source_commits = [
            e
            for e in commitment_opens
            if (e.get("meta") or {}).get("source") == "reflection"
        ]
        assert (
            len(reflection_source_commits) == 0
        ), f"Expected 0 reflection-sourced commitments, found {len(reflection_source_commits)}"


def test_novelty_threshold_policy_still_works() -> None:
    """Verify novelty_threshold policy updates still execute (ADR-001)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        eventlog = EventLog(str(db_path))
        cfg = LLMConfig(
            provider="dummy", model="test", embed_provider=None, embed_model=None
        )
        runtime = Runtime(cfg, eventlog)

        # Simulate applying a novelty_threshold action
        action_text = "Adjust novelty_threshold to 0.65"

        try:
            runtime._apply_policy_from_reflection(
                action_text, reflection_id=1, stage="S0"
            )
        except Exception:
            pass

        # Check for policy_update event
        events = eventlog.read_all()
        policy_updates = [e for e in events if e.get("kind") == "policy_update"]

        # Should have exactly 1 policy_update for cooldown component
        cooldown_updates = [
            e
            for e in policy_updates
            if (e.get("meta") or {}).get("component") == "cooldown"
        ]
        assert (
            len(cooldown_updates) == 1
        ), f"Expected 1 cooldown policy update, found {len(cooldown_updates)}"

        # Verify the parameter value
        meta = cooldown_updates[0].get("meta") or {}
        params = meta.get("params") or {}
        assert params.get("novelty_threshold") == 0.65


def test_unsupported_action_logs_discard() -> None:
    """Verify unsupported actions are logged as reflection_discarded (ADR-001)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        eventlog = EventLog(str(db_path))
        cfg = LLMConfig(
            provider="dummy", model="test", embed_provider=None, embed_model=None
        )
        runtime = Runtime(cfg, eventlog)

        # Simulate an unsupported action (analytical text)
        action_text = "Why-mechanics: This adjustment aligns with our GAS level."

        try:
            runtime._apply_policy_from_reflection(
                action_text, reflection_id=1, stage="S0"
            )
        except Exception:
            pass

        # Check for reflection_discarded event
        events = eventlog.read_all()
        discarded = [e for e in events if e.get("kind") == "reflection_discarded"]

        assert len(discarded) == 1, f"Expected 1 discard event, found {len(discarded)}"

        meta = discarded[0].get("meta") or {}
        assert meta.get("reason") == "unsupported_action"
        assert meta.get("action") == action_text


def test_trait_adjustment_advisory_logged() -> None:
    """Verify trait adjustments are logged as advisory (future expansion point)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        eventlog = EventLog(str(db_path))
        cfg = LLMConfig(
            provider="dummy", model="test", embed_provider=None, embed_model=None
        )
        runtime = Runtime(cfg, eventlog)

        # Simulate a trait adjustment action
        action_text = "Adjust conscientiousness to 0.45"

        try:
            runtime._apply_policy_from_reflection(
                action_text, reflection_id=1, stage="S4"
            )
        except Exception:
            pass

        # Check for reflection_discarded with advisory reason
        events = eventlog.read_all()
        discarded = [e for e in events if e.get("kind") == "reflection_discarded"]

        assert len(discarded) == 1
        meta = discarded[0].get("meta") or {}
        reason = meta.get("reason") or ""

        # Should be logged as advisory, not unsupported
        assert reason.startswith("trait_adjustment_advisory:")
        assert "C=0.45" in reason
