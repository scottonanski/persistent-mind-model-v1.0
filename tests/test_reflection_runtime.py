from pmm.storage.eventlog import EventLog
from pmm.runtime.cooldown import ReflectionCooldown
from pmm.runtime.loop import maybe_reflect


def test_no_reflect_emits_skip_breadcrumb(tmp_path):
    db = tmp_path / "rt1.db"
    log = EventLog(str(db))
    cd = ReflectionCooldown(min_turns=2, min_seconds=60.0)

    # Establish recent baseline time
    cd.reset()
    # Two quick turns, but not enough time
    cd.note_user_turn()
    cd.note_user_turn()
    did, reason = maybe_reflect(log, cd, now=cd.last_ts + 1.0, novelty=1.0)
    assert did is False
    assert reason == "min_time"

    evs = log.read_all()
    skips = [e for e in evs if e["kind"] == "debug"]
    assert skips and (skips[-1].get("meta") or {}).get("reflect_skip") == "min_time"


def test_reflect_resets_cooldown(tmp_path):
    db = tmp_path / "rt2.db"
    log = EventLog(str(db))
    cd = ReflectionCooldown(min_turns=2, min_seconds=1.0)

    cd.reset()
    cd.note_user_turn()
    cd.note_user_turn()

    # Enough time elapsed to pass time gate
    did, reason = maybe_reflect(log, cd, now=cd.last_ts + 2.0, novelty=1.0)
    assert did is True and reason == "ok"

    # Cooldown should reset turns
    assert cd.turns_since == 0

    events = log.read_all()
    kinds = [e["kind"] for e in events]
    # A reflection may be rejected by the acceptance gate; accept either outcome
    if "reflection" in kinds:
        refl = [e for e in events if e["kind"] == "reflection"]
        meta = refl[-1].get("meta") or {}
        tel = meta.get("telemetry") or {}
        assert 0.0 <= tel.get("IAS", 0.0) <= 1.0
        assert 0.0 <= tel.get("GAS", 0.0) <= 1.0
    else:
        # If rejected, a debug breadcrumb is emitted
        rejects = [
            e
            for e in events
            if e.get("kind") == "debug"
            and (e.get("meta") or {}).get("reflection_reject")
        ]
        assert (
            rejects
        ), "expected a reflection_reject breadcrumb when no reflection is emitted"
