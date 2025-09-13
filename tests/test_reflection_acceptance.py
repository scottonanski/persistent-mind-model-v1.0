from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import emit_reflection


def _has_kind(evs, kind):
    return any(e.get("kind") == kind for e in evs)


def _count_kind(evs, kind):
    return sum(1 for e in evs if e.get("kind") == kind)


def test_reflection_accept_audit_only(tmp_path, monkeypatch):
    # Audit-only mode: gate runs, but even when it would reject, reflection is still appended.
    monkeypatch.setenv("PMM_REFLECTION_ACCEPT_ENABLED", "0")
    db = tmp_path / "audit.db"
    log = EventLog(str(db))

    # Too short content should trigger hygiene rejection in gate
    rid = emit_reflection(log, content="short note")
    assert isinstance(rid, int) and rid > 0

    evs = log.read_all()
    # Reflection and its check should be present
    assert _has_kind(evs, "reflection")
    assert _has_kind(evs, "reflection_check")
    # A debug with reflection_reject should also be present (telemetry)
    rejects = [
        e
        for e in evs
        if e.get("kind") == "debug" and (e.get("meta") or {}).get("reflection_reject")
    ]
    assert len(rejects) >= 1


def test_reflection_authoritative_mode_is_audit_only_for_emit(tmp_path, monkeypatch):
    # Authoritative suppression applies to Runtime.reflect() path.
    # emit_reflection() remains audit-only to avoid breaking forced reflection flows in cadence tests.
    monkeypatch.setenv("PMM_REFLECTION_ACCEPT_ENABLED", "1")
    db = tmp_path / "auth.db"
    log = EventLog(str(db))

    rid = emit_reflection(log, content="tiny")  # too short -> gate would reject
    assert isinstance(rid, int) and rid > 0

    evs = log.read_all()
    # Reflection path still occurs (audit-only), and a debug with reflection_reject is appended
    assert _has_kind(evs, "reflection")
    assert _has_kind(evs, "reflection_check")
    rejects = [
        e
        for e in evs
        if e.get("kind") == "debug" and (e.get("meta") or {}).get("reflection_reject")
    ]
    assert len(rejects) >= 1
