from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import _resolve_reflection_cadence


def test_cadence_fallback_to_stage(tmp_path):
    db = tmp_path / "c1.db"
    log = EventLog(str(db))
    mt, ms = _resolve_reflection_cadence(log.read_all())
    assert isinstance(mt, int) and isinstance(ms, int)
    assert mt > 0 and ms >= 0


def test_cadence_policy_override(tmp_path):
    db = tmp_path / "c2.db"
    log = EventLog(str(db))
    # Simulate a policy update that should override fallback
    log.append(
        kind="policy_update",
        content="",
        meta={
            "component": "reflection",
            "params": {"min_turns": 1, "min_time_s": 0},
        },
    )
    mt, ms = _resolve_reflection_cadence(log.read_all())
    assert mt == 1
    assert ms == 0
