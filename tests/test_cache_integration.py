"""Test cache integration with feature flags."""

import os
import tempfile

from pmm.runtime.metrics import get_or_compute_ias_gas
from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model


def test_projection_cache_integration():
    """Test metrics cache integration (always enabled)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)

        # Add events
        log.append("identity_adopt", "TestBot", {"name": "TestBot", "confidence": 0.95})
        log.append("trait_update", "", {"trait": "openness", "delta": 0.02})

        # Cache is always enabled now
        events = log.read_all()
        model = build_self_model(events, eventlog=log)
        assert model["identity"]["name"] == "TestBot"
        assert model["identity"]["traits"]["openness"] == 0.52


def test_metrics_cache_integration():
    """Test metrics cache integration (always enabled)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)

        # Add events
        log.append("identity_adopt", "TestBot", {"name": "TestBot", "confidence": 0.95})
        log.append("autonomy_tick", "", {})

        # Cache is always enabled now
        ias, gas = get_or_compute_ias_gas(log)
        assert isinstance(ias, float)
        assert isinstance(gas, float)


def test_both_caches_together():
    """Test both caches working together (always enabled)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(db_path)

        # Add events
        log.append("identity_adopt", "TestBot", {"name": "TestBot", "confidence": 0.95})
        log.append("trait_update", "", {"trait": "openness", "delta": 0.02})
        log.append("commitment_open", "Task", {"cid": "c1", "text": "Task"})
        log.append("autonomy_tick", "", {})

        # Test projection cache
        events = log.read_all()
        model = build_self_model(events, eventlog=log)
        assert model["identity"]["name"] == "TestBot"
        assert "c1" in model["commitments"]["open"]

        # Test metrics cache
        ias, gas = get_or_compute_ias_gas(log)
        assert isinstance(ias, float)
        assert isinstance(gas, float)
