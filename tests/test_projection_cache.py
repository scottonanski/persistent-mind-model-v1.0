"""Tests for incremental projection cache (Phase 2.1)."""

import os
import tempfile

from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model
from pmm.storage.projection_cache import ProjectionCache


def test_projection_cache_empty_db():
    """Test cache with empty database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = ProjectionCache()

        model = cache.get_model(log)
        assert model["identity"]["name"] is None
        assert model["identity"]["traits"]["openness"] == 0.5
        assert len(model["commitments"]["open"]) == 0

        stats = cache.get_stats()
        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] == 1


def test_projection_cache_matches_full_rebuild():
    """Test that cached projection matches full rebuild."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)

        # Add events
        log.append("identity_adopt", "TestBot", {"name": "TestBot", "confidence": 0.95})
        log.append("trait_update", "", {"trait": "openness", "delta": 0.02})
        log.append("trait_update", "", {"trait": "conscientiousness", "delta": -0.01})
        log.append(
            "commitment_open",
            "Test commitment",
            {"cid": "c1", "text": "Test commitment"},
        )

        # Get from cache
        cache = ProjectionCache()
        cached_model = cache.get_model(log)

        # Get from full rebuild
        events = log.read_all()
        full_model = build_self_model(events)

        # Should match exactly
        assert cached_model == full_model
        assert cached_model["identity"]["name"] == "TestBot"
        assert cached_model["identity"]["traits"]["openness"] == 0.52
        assert cached_model["identity"]["traits"]["conscientiousness"] == 0.49
        assert "c1" in cached_model["commitments"]["open"]


def test_projection_cache_incremental_updates():
    """Test that cache correctly applies incremental updates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = ProjectionCache()

        # Initial state
        log.append("identity_adopt", "Bot1", {"name": "Bot1", "confidence": 0.95})
        model1 = cache.get_model(log)
        assert model1["identity"]["name"] == "Bot1"

        # Add more events
        log.append("trait_update", "", {"trait": "openness", "delta": 0.05})
        log.append("commitment_open", "Task 1", {"cid": "c1", "text": "Task 1"})

        # Get updated model (should use cache + incremental)
        model2 = cache.get_model(log)
        assert model2["identity"]["name"] == "Bot1"
        assert model2["identity"]["traits"]["openness"] == 0.55
        assert "c1" in model2["commitments"]["open"]

        # Verify stats
        stats = cache.get_stats()
        assert stats["cache_misses"] == 2  # Initial + update
        assert stats["events_processed"] == 3


def test_projection_cache_commitment_lifecycle():
    """Test cache handles commitment open/close/expire correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = ProjectionCache()

        # Open commitment
        log.append("commitment_open", "Task 1", {"cid": "c1", "text": "Task 1"})
        model1 = cache.get_model(log)
        assert "c1" in model1["commitments"]["open"]

        # Add evidence and close
        log.append("evidence_candidate", "", {"cid": "c1", "evidence_type": "done"})
        log.append("commitment_close", "", {"cid": "c1"})
        model2 = cache.get_model(log)
        assert "c1" not in model2["commitments"]["open"]

        # Open another and expire it
        log.append("commitment_open", "Task 2", {"cid": "c2", "text": "Task 2"})
        log.append("commitment_expire", "", {"cid": "c2", "reason": "timeout"})
        model3 = cache.get_model(log)
        assert "c2" not in model3["commitments"]["open"]
        assert "c2" in model3["commitments"]["expired"]


def test_projection_cache_multi_trait_update():
    """Test cache handles multi-trait updates (S4 schema)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = ProjectionCache()

        log.append("identity_adopt", "Bot", {"name": "Bot", "confidence": 0.95})

        # Multi-trait update
        log.append(
            "trait_update",
            "",
            {
                "delta": {
                    "openness": 0.02,
                    "conscientiousness": -0.01,
                    "extraversion": 0.03,
                }
            },
        )

        model = cache.get_model(log)
        assert model["identity"]["traits"]["openness"] == 0.52
        assert model["identity"]["traits"]["conscientiousness"] == 0.49
        assert model["identity"]["traits"]["extraversion"] == 0.53
        assert model["identity"]["traits"]["agreeableness"] == 0.50  # unchanged
        assert model["identity"]["traits"]["neuroticism"] == 0.50  # unchanged


def test_projection_cache_identity_clear():
    """Test cache handles identity_clear correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = ProjectionCache()

        log.append("identity_adopt", "Bot1", {"name": "Bot1", "confidence": 0.95})
        model1 = cache.get_model(log)
        assert model1["identity"]["name"] == "Bot1"

        log.append("identity_clear", "", {})
        model2 = cache.get_model(log)
        assert model2["identity"]["name"] is None


def test_projection_cache_verification():
    """Test periodic verification against full rebuild."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)

        # Set verify_every to small number for testing
        cache = ProjectionCache(verify_every=5)

        # Add events incrementally to trigger verification
        for i in range(10):
            log.append("trait_update", "", {"trait": "openness", "delta": 0.01})
            # Get model after each event to trigger incremental updates
            if i % 2 == 1:  # Every other event
                cache.get_model(log)

        # Final get to ensure all events processed
        cache.get_model(log)

        # Should have verified at least once (at 5 events boundary)
        stats = cache.get_stats()
        assert stats["verifications_passed"] >= 1
        assert stats["verifications_failed"] == 0


def test_projection_cache_get_identity():
    """Test get_identity convenience method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = ProjectionCache()

        log.append("identity_adopt", "TestBot", {"name": "TestBot", "confidence": 0.95})
        log.append("trait_update", "", {"trait": "openness", "delta": 0.05})

        identity = cache.get_identity(log)
        assert identity["name"] == "TestBot"
        assert identity["traits"]["openness"] == 0.55


def test_projection_cache_clear():
    """Test cache clear functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = ProjectionCache()

        log.append("identity_adopt", "Bot", {"name": "Bot", "confidence": 0.95})
        model1 = cache.get_model(log)
        assert model1["identity"]["name"] == "Bot"

        # Clear cache
        cache.clear()
        stats = cache.get_stats()
        assert stats["last_id"] == 0
        assert stats["events_processed"] == 0
        assert not stats["cached"]

        # Should rebuild from scratch
        model2 = cache.get_model(log)
        assert model2["identity"]["name"] == "Bot"


def test_projection_cache_determinism():
    """Test that cache produces deterministic results."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)

        # Add events
        log.append("identity_adopt", "Bot", {"name": "Bot", "confidence": 0.95})
        for i in range(10):
            log.append("trait_update", "", {"trait": "openness", "delta": 0.01})

        # Get model multiple times
        cache = ProjectionCache()
        results = [cache.get_model(log) for _ in range(5)]

        # All results should be identical
        for result in results[1:]:
            assert result == results[0]


def test_projection_cache_large_incremental_update():
    """Test cache with many incremental updates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = ProjectionCache(verify_every=100)

        log.append("identity_adopt", "Bot", {"name": "Bot", "confidence": 0.95})

        # Add many events incrementally
        for i in range(500):
            log.append("trait_update", "", {"trait": "openness", "delta": 0.001})
            if i % 50 == 0:
                # Get model periodically
                cache.get_model(log)

        # Final model
        final_model = cache.get_model(log)

        # Verify against full rebuild
        events = log.read_all()
        full_model = build_self_model(events)
        assert final_model == full_model

        # Check stats
        stats = cache.get_stats()
        assert stats["events_processed"] == 501  # 1 identity + 500 traits
        assert stats["verifications_passed"] >= 5  # At 100, 200, 300, 400, 500


def test_projection_cache_commitment_snooze():
    """Test cache handles commitment_snooze correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = ProjectionCache()

        log.append("commitment_open", "Task", {"cid": "c1", "text": "Task"})
        log.append("commitment_snooze", "", {"cid": "c1", "until_tick": 100})

        model = cache.get_model(log)
        assert "c1" in model["commitments"]["open"]
        assert model["commitments"]["open"]["c1"]["snoozed_until"] == 100


def test_projection_cache_hit_rate():
    """Test cache hit rate with repeated queries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = ProjectionCache()

        log.append("identity_adopt", "Bot", {"name": "Bot", "confidence": 0.95})

        # First call - cache miss
        model1 = cache.get_model(log)

        # Subsequent calls without new events - cache hits
        for _ in range(10):
            model = cache.get_model(log)
            assert model == model1

        stats = cache.get_stats()
        assert stats["cache_hits"] == 10
        assert stats["cache_misses"] == 1
        assert stats["hit_rate"] > 0.9
