"""Tests for identity adoption flow with checkpoint, reflection, and trait updates."""

import pytest
import tempfile
import os
from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import AutonomyLoop
from pmm.runtime.cooldown import ReflectionCooldown


def test_identity_adoption_flow():
    """Test the complete identity adoption flow: checkpoint → trait update → reflection."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "adoption_flow.db")
        log = EventLog(db_path)
        cooldown = ReflectionCooldown()
        loop = AutonomyLoop(eventlog=log, cooldown=cooldown)

        # Step 1: Initial identity adoption via explicit handler
        loop.handle_identity_adopt(
            "Alpha",
            meta={
                "source": "test",
                "intent": "assign_assistant_name",
                "confidence": 0.9,
            },
        )

        events = log.read_all()
        kinds = [e["kind"] for e in events]

        # ✅ Identity checkpoint recorded
        assert "identity_checkpoint" in kinds
        checkpoint = next(e for e in events if e["kind"] == "identity_checkpoint")
        assert "traits" in checkpoint["meta"]
        assert "commitments" in checkpoint["meta"]

        # ✅ Trait updates (optional). If present, ensure bounded deltas
        trait_updates = [e for e in events if e["kind"] == "trait_update"]
        for trait_update in trait_updates:
            if "delta" in trait_update["meta"]:
                delta_values = list(trait_update["meta"]["delta"].values())
                for delta in delta_values:
                    assert -0.05 <= delta <= 0.05

        # ✅ Reflection triggered by adoption (content may vary)
        reflections = [e for e in events if e["kind"] == "reflection"]
        assert len(reflections) > 0

        # Step 2: Open a commitment under Alpha (include text in meta for projection)
        log.append(
            kind="commitment_open",
            content="As Alpha, I will explore persistence.",
            meta={
                "cid": "test_cid_1",
                "text": "As Alpha, I will explore persistence.",
            },
        )

        # Step 3: Adopt new identity → Echo using explicit handler
        loop.handle_identity_adopt(
            "Echo",
            meta={
                "source": "test",
                "intent": "assign_assistant_name",
                "confidence": 0.9,
            },
        )

        events = log.read_all()

        # ✅ Commitment rebind should occur
        rebinds = [e for e in events if e["kind"] == "commitment_rebind"]
        assert len(rebinds) > 0
        assert any(
            "Alpha" in r["meta"]["old_name"] and "Echo" in r["meta"]["new_name"]
            for r in rebinds
        )

        # ✅ Identity projection summary should be emitted with details
        projections = [e for e in events if e["kind"] == "identity_projection"]
        assert len(projections) >= 1
        proj = projections[-1]
        assert proj["meta"]["previous_identity"] == "Alpha"
        assert proj["meta"]["current_identity"] == "Echo"
        assert "test_cid_1" in proj["meta"].get("rebound_commitments", [])

        # ✅ Reflection after second adoption mentions Echo (no strict trigger meta dependency)
        # Find reflections appended after the second identity_adopt event
        last_adopt_id = max(e["id"] for e in events if e["kind"] == "identity_adopt")
        reflections_after = [
            e
            for e in events
            if e["kind"] == "reflection" and int(e["id"]) > int(last_adopt_id)
        ]
        assert any("Echo" in (r["content"] or "") for r in reflections_after)


if __name__ == "__main__":
    pytest.main([__file__])
