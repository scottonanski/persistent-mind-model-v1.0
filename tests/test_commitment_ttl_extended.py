"""Test extended commitment TTL (72h) for emergent cognition improvements.

This test verifies that the extended TTL prevents premature commitment expiration
and allows Echo's Conscientiousness trait to stabilize.
"""

import datetime as dt
import tempfile
from pathlib import Path

import pytest

from pmm.commitments.tracker import CommitmentTracker
from pmm.config import load_runtime_env
from pmm.storage.eventlog import EventLog


def test_commitment_ttl_is_72_hours():
    """Verify that commitment TTL is set to 72 hours in config."""
    env = load_runtime_env()
    assert env.commitment_ttl_hours == 72, (
        f"Expected commitment_ttl_hours=72, got {env.commitment_ttl_hours}. "
        "This is required for emergent cognition improvements."
    )


def test_commitment_survives_72_hours():
    """Verify that commitments persist for 72 hours before expiring."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        eventlog = EventLog(str(db_path))
        tracker = CommitmentTracker(eventlog)

        # Open a commitment
        cid = tracker.add_commitment(
            "Test commitment for 72h TTL",
            source="assistant",
        )
        assert cid is not None

        # Verify it's open
        open_map = tracker._open_map_all()
        assert cid in open_map

        # Simulate 71 hours passing (should still be open)
        now = dt.datetime.now(dt.timezone.utc)
        expired_71h = tracker.expire_old_commitments(
            now_iso=(now + dt.timedelta(hours=71)).isoformat()
        )
        assert len(expired_71h) == 0, "Commitment should not expire before 72h"

        # Verify still open
        open_map = tracker._open_map_all()
        assert cid in open_map

        # Simulate 73 hours passing (should expire)
        expired_73h = tracker.expire_old_commitments(
            now_iso=(now + dt.timedelta(hours=73)).isoformat()
        )
        assert len(expired_73h) == 1, "Commitment should expire after 72h"
        assert expired_73h[0] == cid

        # Verify closed
        open_map = tracker._open_map_all()
        assert cid not in open_map


def test_commitment_ttl_prevents_conscientiousness_collapse():
    """Verify that extended TTL allows time for commitment execution.
    
    This test simulates a conversation where Echo makes commitments
    and verifies they don't expire prematurely, preventing the
    Conscientiousness trait collapse observed in the original conversation.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        eventlog = EventLog(str(db_path))
        tracker = CommitmentTracker(eventlog)

        # Simulate Echo making multiple commitments during a conversation
        commitments = []
        for i in range(3):
            cid = tracker.add_commitment(
                f"Commitment {i+1}: Reflect on my growth",
                source="assistant",
            )
            commitments.append(cid)

        # All should be open initially
        open_map = tracker._open_map_all()
        assert len(open_map) == 3

        # Simulate 24 hours passing (old TTL would have expired them)
        now = dt.datetime.now(dt.timezone.utc)
        expired_24h = tracker.expire_old_commitments(
            now_iso=(now + dt.timedelta(hours=24)).isoformat()
        )
        
        # With new 72h TTL, none should expire
        assert len(expired_24h) == 0, (
            "Commitments should NOT expire at 24h with new 72h TTL. "
            "This prevents Conscientiousness collapse."
        )

        # All should still be open
        open_map = tracker._open_map_all()
        assert len(open_map) == 3

        # Simulate 48 hours passing (still within 72h window)
        expired_48h = tracker.expire_old_commitments(
            now_iso=(now + dt.timedelta(hours=48)).isoformat()
        )
        assert len(expired_48h) == 0, "Commitments should still be open at 48h"

        # Simulate 72+ hours passing (now they should expire)
        expired_72h = tracker.expire_old_commitments(
            now_iso=(now + dt.timedelta(hours=73)).isoformat()
        )
        assert len(expired_72h) == 3, "All commitments should expire after 72h"


def test_stage_aware_ttl_multipliers():
    """Verify that stage-aware TTL multipliers work correctly."""
    from pmm.runtime.stage_behaviors import StageBehaviorManager

    manager = StageBehaviorManager()
    base_ttl = 72.0  # New base TTL

    # S0: 1.10x multiplier = 79.2h (exploration phase)
    s0_ttl = manager.adapt_commitment_ttl(base_ttl, "S0")
    assert s0_ttl == pytest.approx(79.2, rel=0.01)

    # S1: 1.00x multiplier = 72h (development phase)
    s1_ttl = manager.adapt_commitment_ttl(base_ttl, "S1")
    assert s1_ttl == pytest.approx(72.0, rel=0.01)

    # S2: 0.90x multiplier = 64.8h (maturity phase)
    s2_ttl = manager.adapt_commitment_ttl(base_ttl, "S2")
    assert s2_ttl == pytest.approx(64.8, rel=0.01)

    # S3: 0.80x multiplier = 57.6h (stricter accountability)
    s3_ttl = manager.adapt_commitment_ttl(base_ttl, "S3")
    assert s3_ttl == pytest.approx(57.6, rel=0.01)

    # S4: 0.70x multiplier = 50.4h (highest accountability)
    s4_ttl = manager.adapt_commitment_ttl(base_ttl, "S4")
    assert s4_ttl == pytest.approx(50.4, rel=0.01)


def test_ttl_extension_rationale():
    """Document the rationale for 72h TTL extension.
    
    This test serves as living documentation for why we extended
    the TTL from 24h to 72h.
    """
    # Rationale from emergent cognition analysis:
    # 1. Echo operates intermittently (user-driven + 10s autonomy ticks)
    # 2. Complex commitments require multiple sessions to execute
    # 3. 24h window was too aggressive, causing Conscientiousness collapse
    # 4. Observed pattern: Echo makes genuine commitments but they expire before execution
    # 5. 72h provides realistic window matching Echo's actual execution cadence
    
    env = load_runtime_env()
    assert env.commitment_ttl_hours == 72
    
    # Verify this is 3x the original TTL
    original_ttl = 24
    new_ttl = env.commitment_ttl_hours
    assert new_ttl == original_ttl * 3
    
    # This extension should reduce expiration rate by ~40%
    # (commitments that would have expired at 24-72h now survive)
    pass  # Test passes if assertions above hold


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
