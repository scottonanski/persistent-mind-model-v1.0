import tempfile

from pmm.runtime.cooldown import ReflectionCooldown
from pmm.runtime.loop import AutonomyLoop
from pmm.storage.eventlog import EventLog


def test_pmm_native_reflection_is_emitted_and_ontology_locked():
    with tempfile.TemporaryDirectory() as tmpdir:
        log = EventLog(f"{tmpdir}/r.db")
        loop = AutonomyLoop(eventlog=log, cooldown=ReflectionCooldown())

        # Force an adopt → should force a reflection immediately (same tick)
        loop.handle_identity_adopt(
            "Echo",
            meta={
                "source": "test",
                "intent": "assign_assistant_name",
                "confidence": 0.9,
            },
        )

        evs = log.read_all()
        refl = [e for e in evs if e["kind"] == "reflection"]
        assert len(refl) >= 1

        text = refl[-1]["content"].lower()
        # must mention PMM terms
        assert any(
            k in text for k in ("ledger", "traits", "commitment", "policy", "scene")
        )
        # must NOT contain assistant filler
        assert "how can i assist" not in text
        assert "journal" not in text
        assert "learn more" not in text
