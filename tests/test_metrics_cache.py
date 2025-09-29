"""Tests for incremental metrics cache (Phase 2.2)."""

import tempfile
import os

from pmm.storage.eventlog import EventLog
from pmm.runtime.metrics import compute_ias_gas
from pmm.runtime.metrics_cache import MetricsCache


def test_metrics_cache_empty_db():
    """Test cache with empty database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = MetricsCache()

        ias, gas = cache.get_metrics(log)
        assert ias == 0.0
        assert gas == 0.0

        stats = cache.get_stats()
        # Empty DB returns immediately without incrementing counters
        assert stats["events_processed"] == 0


def test_metrics_cache_matches_full_computation():
    """Test that cached metrics match full computation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)

        # Add events
        log.append("identity_adopt", "TestBot", {"name": "TestBot", "confidence": 0.95})
        log.append("autonomy_tick", "", {})
        log.append("autonomy_tick", "", {})
        log.append("commitment_open", "Task 1", {"cid": "c1", "text": "Task 1"})
        log.append("autonomy_tick", "", {})

        # Get from cache
        cache = MetricsCache()
        cached_ias, cached_gas = cache.get_metrics(log)

        # Get from full computation
        events = log.read_all()
        full_ias, full_gas = compute_ias_gas(events)

        # Should match (within floating point tolerance)
        assert abs(cached_ias - full_ias) < 0.001
        assert abs(cached_gas - full_gas) < 0.001


def test_metrics_cache_incremental_updates():
    """Test that cache correctly applies incremental updates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = MetricsCache()

        # Initial state
        log.append("identity_adopt", "Bot", {"name": "Bot", "confidence": 0.95})
        log.append("autonomy_tick", "", {})
        ias1, gas1 = cache.get_metrics(log)

        # Add more events
        log.append("commitment_open", "Task", {"cid": "c1", "text": "Task"})
        log.append("autonomy_tick", "", {})
        ias2, gas2 = cache.get_metrics(log)

        # GAS should increase due to commitment
        assert gas2 > gas1

        # Verify stats
        stats = cache.get_stats()
        assert stats["cache_misses"] == 2  # Initial + update
        assert stats["recomputations"] == 2


def test_metrics_cache_identity_stability():
    """Test cache handles identity stability bonuses correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = MetricsCache()

        # Adopt identity
        log.append("identity_adopt", "Bot", {"name": "Bot", "confidence": 0.95})

        # Add ticks to trigger stability bonus (every 5 ticks)
        for _ in range(10):
            log.append("autonomy_tick", "", {})

        ias, gas = cache.get_metrics(log)

        # Should have stability bonuses
        assert ias > 0.0

        # Verify against full computation
        events = log.read_all()
        full_ias, full_gas = compute_ias_gas(events)
        assert abs(ias - full_ias) < 0.001


def test_metrics_cache_commitment_novelty():
    """Test cache handles commitment novelty correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = MetricsCache()

        # Open same commitment twice (not novel)
        log.append("commitment_open", "Task", {"cid": "c1", "text": "Task"})
        log.append("autonomy_tick", "", {})
        ias1, gas1 = cache.get_metrics(log)

        log.append("commitment_open", "Task", {"cid": "c2", "text": "Task"})
        log.append("autonomy_tick", "", {})
        ias2, gas2 = cache.get_metrics(log)

        # Second commitment should not increase GAS (not novel)
        # (accounting for decay)
        assert gas2 <= gas1 * 1.01  # Allow small increase from rounding


def test_metrics_cache_decay():
    """Test cache handles decay correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = MetricsCache()

        # Build up some metrics
        log.append("identity_adopt", "Bot", {"name": "Bot", "confidence": 0.95})
        log.append("commitment_open", "Task", {"cid": "c1", "text": "Task"})
        ias1, gas1 = cache.get_metrics(log)

        # Add many ticks to apply decay
        for _ in range(100):
            log.append("autonomy_tick", "", {})

        ias2, gas2 = cache.get_metrics(log)

        # Verify against full computation
        events = log.read_all()
        full_ias, full_gas = compute_ias_gas(events)
        assert abs(ias2 - full_ias) < 0.001
        assert abs(gas2 - full_gas) < 0.001


def test_metrics_cache_recomputation():
    """Test that cache recomputes on new events."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = MetricsCache()

        # Add events incrementally
        log.append("identity_adopt", "Bot", {"name": "Bot", "confidence": 0.95})
        ias1, gas1 = cache.get_metrics(log)

        for _ in range(5):
            log.append("autonomy_tick", "", {})

        ias2, gas2 = cache.get_metrics(log)

        # Should have recomputed
        stats = cache.get_stats()
        assert stats["recomputations"] == 2  # Initial + after ticks
        assert stats["cache_misses"] == 2


def test_metrics_cache_clear():
    """Test cache clear functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = MetricsCache()

        log.append("identity_adopt", "Bot", {"name": "Bot", "confidence": 0.95})
        log.append("commitment_open", "Task", {"cid": "c1", "text": "Task"})
        ias1, gas1 = cache.get_metrics(log)
        assert ias1 > 0 or gas1 > 0

        # Clear cache
        cache.clear()
        stats = cache.get_stats()
        assert stats["last_id"] == 0
        assert stats["events_processed"] == 0
        assert stats["ias"] == 0.0
        assert stats["gas"] == 0.0

        # Should rebuild from scratch
        ias2, gas2 = cache.get_metrics(log)
        assert abs(ias2 - ias1) < 0.001
        assert abs(gas2 - gas1) < 0.001


def test_metrics_cache_determinism():
    """Test that cache produces deterministic results."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)

        # Add events
        log.append("identity_adopt", "Bot", {"name": "Bot", "confidence": 0.95})
        for _ in range(10):
            log.append("autonomy_tick", "", {})
        log.append("commitment_open", "Task", {"cid": "c1", "text": "Task"})

        # Get metrics multiple times
        cache = MetricsCache()
        results = [cache.get_metrics(log) for _ in range(5)]

        # All results should be identical
        for result in results[1:]:
            assert result == results[0]


def test_metrics_cache_large_update():
    """Test cache with many events."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = MetricsCache()

        log.append("identity_adopt", "Bot", {"name": "Bot", "confidence": 0.95})

        # Add many events
        for _ in range(100):
            log.append("autonomy_tick", "", {})

        # Get metrics
        final_ias, final_gas = cache.get_metrics(log)

        # Verify against full computation
        events = log.read_all()
        full_ias, full_gas = compute_ias_gas(events)
        assert abs(final_ias - full_ias) < 0.001
        assert abs(final_gas - full_gas) < 0.001

        # Check stats
        stats = cache.get_stats()
        assert stats["events_processed"] == 101  # 1 identity + 100 ticks
        assert stats["recomputations"] >= 1


def test_metrics_cache_hit_rate():
    """Test cache hit rate with repeated queries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = MetricsCache()

        log.append("identity_adopt", "Bot", {"name": "Bot", "confidence": 0.95})

        # First call - cache miss
        ias1, gas1 = cache.get_metrics(log)

        # Subsequent calls without new events - cache hits
        for _ in range(10):
            ias, gas = cache.get_metrics(log)
            assert ias == ias1
            assert gas == gas1

        stats = cache.get_stats()
        assert stats["cache_hits"] == 10
        assert stats["cache_misses"] == 1
        assert stats["hit_rate"] > 0.9


def test_metrics_cache_flip_flop_penalty():
    """Test cache handles identity flip-flop penalty."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = MetricsCache()

        # Adopt identity
        log.append("identity_adopt", "Bot1", {"name": "Bot1", "confidence": 0.95})
        log.append("autonomy_tick", "", {})
        ias1, _ = cache.get_metrics(log)

        # Flip-flop within window (should incur penalty)
        log.append("identity_adopt", "Bot2", {"name": "Bot2", "confidence": 0.95})
        log.append("autonomy_tick", "", {})
        ias2, _ = cache.get_metrics(log)

        # Verify against full computation
        events = log.read_all()
        full_ias, _ = compute_ias_gas(events)
        assert abs(ias2 - full_ias) < 0.001


def test_metrics_cache_trait_updates():
    """Test cache updates trait multipliers correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = MetricsCache()

        # Initial state
        log.append("identity_adopt", "Bot", {"name": "Bot", "confidence": 0.95})
        log.append("trait_update", "", {"trait": "openness", "delta": 0.2})
        log.append("trait_update", "", {"trait": "conscientiousness", "delta": 0.2})

        # Add commitment (should be affected by trait multipliers)
        log.append("commitment_open", "Task", {"cid": "c1", "text": "Task"})
        _, gas1 = cache.get_metrics(log)

        # Verify against full computation
        events = log.read_all()
        _, full_gas = compute_ias_gas(events)
        assert abs(gas1 - full_gas) < 0.001


def test_metrics_cache_reflection_bonus():
    """Test cache handles reflection identity bonus."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)
        cache = MetricsCache()

        log.append("identity_adopt", "Bot", {"name": "Bot", "confidence": 0.95})
        ias1, _ = cache.get_metrics(log)

        # Add identity-linked reflection
        log.append(
            "reflection",
            "I am reflecting on my identity and what it means to be Bot",
            {},
        )
        ias2, _ = cache.get_metrics(log)

        # IAS should increase slightly
        assert ias2 >= ias1
