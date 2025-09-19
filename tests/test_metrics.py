from pmm.runtime.metrics import compute_ias_gas
from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import emit_reflection, maybe_reflect
from pmm.runtime.cooldown import ReflectionCooldown


def test_compute_ias_gas_bounds():
    evs = [
        {"kind": "commitment_open"},
        {"kind": "commitment_close"},
        {"kind": "reflection"},
        {"kind": "commitment_open"},
    ]
    ias, gas = compute_ias_gas(evs)
    assert 0.0 <= ias <= 1.0
    assert 0.0 <= gas <= 1.0

    # More closes than opens still holds the IAS baseline (identity stability rules)
    evs2 = [
        {"kind": "commitment_open"},
        {"kind": "commitment_close"},
        {"kind": "commitment_close"},
        {"kind": "commitment_close"},
    ]
    ias2, gas2 = compute_ias_gas(evs2)
    assert 0.5 <= ias2 <= 1.0
    assert 0.0 < gas2 <= 1.0


def test_reflection_emits_telemetry(tmp_path):
    db = tmp_path / "m.db"
    log = EventLog(str(db))

    # Emit reflection via helper, ensure telemetry appended
    emit_reflection(log, content="note")
    events = log.read_all()
    # Find the reflection event and assert embedded telemetry fields
    refl = [e for e in events if e["kind"] == "reflection"]
    assert refl, "no reflection event emitted"
    meta = refl[-1].get("meta") or {}
    tel = meta.get("telemetry") or {}
    assert 0.0 <= tel.get("IAS", 0.0) <= 1.0
    assert 0.0 <= tel.get("GAS", 0.0) <= 1.0


def test_no_reflect_emits_skip_breadcrumb(tmp_path):
    db = tmp_path / "r.db"
    log = EventLog(str(db))
    cd = ReflectionCooldown(min_turns=2, min_seconds=60.0)

    # Only one turn -> expect min_turns skip
    cd.note_user_turn()
    did, reason = maybe_reflect(log, cd, now=0.0, novelty=1.0)
    assert did is False and reason == "min_turns"

    evs = log.read_all()
    skip = [
        e
        for e in evs
        if e["kind"] == "debug" and (e.get("meta") or {}).get("reflect_skip")
    ]
    assert skip and skip[-1]["meta"]["reflect_skip"] in ("min_turns", "min_time")
