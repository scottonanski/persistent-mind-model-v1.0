"""Test cache integration with feature flags."""

import tempfile
import os

from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model_cached
from pmm.runtime.metrics import get_or_compute_ias_gas


def test_projection_cache_integration_disabled():
    """Test projection cache integration when disabled (default)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)

        # Add events
        log.append("identity_adopt", "TestBot", {"name": "TestBot", "confidence": 0.95})
        log.append("trait_update", "", {"trait": "openness", "delta": 0.02})

        # Should work without cache (default)
        model = build_self_model_cached(log)
        assert model["identity"]["name"] == "TestBot"
        assert model["identity"]["traits"]["openness"] == 0.52


def test_projection_cache_integration_enabled():
    """Test projection cache integration when enabled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)

        # Add events
        log.append("identity_adopt", "TestBot", {"name": "TestBot", "confidence": 0.95})
        log.append("trait_update", "", {"trait": "openness", "delta": 0.02})

        # Enable cache via environment
        os.environ["PMM_USE_PROJECTION_CACHE"] = "true"
        try:
            # Force reload of config
            import importlib
            import pmm.config

            importlib.reload(pmm.config)

            model = build_self_model_cached(log)
            assert model["identity"]["name"] == "TestBot"
            assert model["identity"]["traits"]["openness"] == 0.52
        finally:
            os.environ.pop("PMM_USE_PROJECTION_CACHE", None)
            importlib.reload(pmm.config)


def test_metrics_cache_integration_disabled():
    """Test metrics cache integration when disabled (default)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)

        # Add events
        log.append("identity_adopt", "TestBot", {"name": "TestBot", "confidence": 0.95})
        log.append("autonomy_tick", "", {})

        # Should work without cache (default)
        ias, gas = get_or_compute_ias_gas(log)
        assert isinstance(ias, float)
        assert isinstance(gas, float)


def test_metrics_cache_integration_enabled():
    """Test metrics cache integration when enabled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)

        # Add events
        log.append("identity_adopt", "TestBot", {"name": "TestBot", "confidence": 0.95})
        log.append("autonomy_tick", "", {})

        # Enable cache via environment
        os.environ["PMM_USE_METRICS_CACHE"] = "true"
        try:
            # Force reload of config
            import importlib
            import pmm.config

            importlib.reload(pmm.config)

            ias, gas = get_or_compute_ias_gas(log)
            assert isinstance(ias, float)
            assert isinstance(gas, float)
        finally:
            os.environ.pop("PMM_USE_METRICS_CACHE", None)
            importlib.reload(pmm.config)


def test_both_caches_enabled():
    """Test both caches enabled together."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)

        # Add events
        log.append("identity_adopt", "TestBot", {"name": "TestBot", "confidence": 0.95})
        log.append("trait_update", "", {"trait": "openness", "delta": 0.02})
        log.append("commitment_open", "Task", {"cid": "c1", "text": "Task"})
        log.append("autonomy_tick", "", {})

        # Enable both caches
        os.environ["PMM_USE_PROJECTION_CACHE"] = "true"
        os.environ["PMM_USE_METRICS_CACHE"] = "true"
        try:
            # Force reload of config
            import importlib
            import pmm.config

            importlib.reload(pmm.config)

            # Test projection
            model = build_self_model_cached(log)
            assert model["identity"]["name"] == "TestBot"
            assert "c1" in model["commitments"]["open"]

            # Test metrics
            ias, gas = get_or_compute_ias_gas(log)
            assert isinstance(ias, float)
            assert isinstance(gas, float)
        finally:
            os.environ.pop("PMM_USE_PROJECTION_CACHE", None)
            os.environ.pop("PMM_USE_METRICS_CACHE", None)
            importlib.reload(pmm.config)
