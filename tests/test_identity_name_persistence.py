import tempfile

from pmm.runtime.cooldown import ReflectionCooldown
from pmm.runtime.loop import AutonomyLoop
from pmm.storage.eventlog import EventLog


def test_name_persistence_updates_and_event_emitted():
    with tempfile.TemporaryDirectory() as tmpdir:
        log = EventLog(f"{tmpdir}/n.db")
        loop = AutonomyLoop(eventlog=log, cooldown=ReflectionCooldown())

        loop.handle_identity_adopt(
            "Alpha",
            meta={
                "source": "test",
                "intent": "assign_assistant_name",
                "confidence": 0.9,
            },
        )
        loop.handle_identity_adopt(
            "Echo",
            meta={
                "source": "test",
                "intent": "assign_assistant_name",
                "confidence": 0.9,
            },
        )

        evs = log.read_all()
        adopts = [e for e in evs if e["kind"] == "identity_adopt"]
        assert adopts[-1]["content"] == "Echo"

        name_events = [e for e in evs if e["kind"] == "name_updated"]
        assert len(name_events) >= 1
        assert name_events[-1]["meta"]["new_name"] == "Echo"
