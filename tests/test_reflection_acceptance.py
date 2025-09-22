from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import emit_reflection


def _has_kind(evs, kind):
    return any(e.get("kind") == kind for e in evs)


def _count_kind(evs, kind):
    return sum(1 for e in evs if e.get("kind") == kind)


def test_reflection_accept_is_authoritative_for_emit(tmp_path):
    # Current implementation applies authoritative acceptance for emit_reflection.
    db = tmp_path / "audit.db"
    log = EventLog(str(db))

    # Too short content should trigger hygiene rejection in gate and skip append
    rid = emit_reflection(log, content="short note")
    assert rid is None

    evs = log.read_all()
    # No reflection or check appended when rejected
    assert not _has_kind(evs, "reflection")
    assert not _has_kind(evs, "reflection_check")
    # A debug with reflection_reject should be present (telemetry)
    rejects = [
        e
        for e in evs
        if e.get("kind") == "reflection_rejected"
        and (e.get("meta") or {}).get("reason")
    ]
    assert len(rejects) >= 1


def test_reflection_forced_path_generates_fallback_when_rejected(tmp_path):
    # Forced reflections that would otherwise be rejected generate a fallback summary and proceed.
    db = tmp_path / "auth.db"
    log = EventLog(str(db))

    rid = emit_reflection(log, content="", forced=True)
    # Forced path should emit a reflection with synthesized content
    assert isinstance(rid, int) and rid > 0

    evs = log.read_all()
    assert _has_kind(evs, "reflection")
    # A debug with reflection_reject may be present from initial attempt
    rejects = [
        e
        for e in evs
        if e.get("kind") == "reflection_rejected"
        and (e.get("meta") or {}).get("reason")
    ]
    assert isinstance(rejects, list)
