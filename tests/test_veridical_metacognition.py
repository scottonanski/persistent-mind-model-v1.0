"""Integration tests for veridical metacognition safeguards."""

from __future__ import annotations

from pathlib import Path

from pmm.llm.factory import LLMConfig
from pmm.runtime.cooldown import ReflectionCooldown
from pmm.runtime.loop import AutonomyLoop, Runtime
from pmm.runtime.loop import pipeline as _pipeline
from pmm.runtime.loop.io import append_response
from pmm.runtime.loop.reflection import emit_reflection
from pmm.storage.eventlog import EventLog


def _make_runtime(tmp_path: Path) -> Runtime:
    db = tmp_path / "veridical.db"
    cfg = LLMConfig(provider="openai", model="gpt-3.5-turbo")
    return Runtime(cfg, EventLog(str(db)))


def _make_loop(tmp_path: Path) -> AutonomyLoop:
    db = tmp_path / "loop.db"
    log = EventLog(str(db))
    loop = AutonomyLoop(
        eventlog=log,
        cooldown=ReflectionCooldown(),
        interval_seconds=0.1,
        bootstrap_identity=False,
    )
    loop.stop()
    return loop


def test_evidence_gated_reflection_rejects_empty(tmp_path: Path):
    log_empty = EventLog(str(tmp_path / "reflections_empty.db"))
    log_nonempty = EventLog(str(tmp_path / "reflections_nonempty.db"))

    rid_empty = emit_reflection(
        log_empty,
        content="",
        events=[],
        llm_generate=lambda _: "",
    )
    assert rid_empty is None
    assert not [ev for ev in log_empty.read_all() if ev["kind"] == "reflection"]

    rid = emit_reflection(
        log_nonempty,
        content="",
        events=[],
        llm_generate=lambda _: "Reflection covering ledger, traits, and commitments.",
    )
    assert rid is not None
    stored = log_nonempty.get_event(int(rid))
    assert stored["kind"] == "reflection"
    assert stored["content"] == "Reflection covering ledger, traits, and commitments."


def test_reply_pipeline_persists_claims(tmp_path: Path):
    runtime = _make_runtime(tmp_path)
    runtime.record_claimed_reflection_ids([9, "3", 9, -1])

    reply, response_eid = _pipeline.reply_post_llm(
        runtime,
        reply="Handled reflection accountability.",
        meta={"source": "test_suite"},
        skip_embedding=True,
        apply_validators=False,
    )

    assert reply == "Handled reflection accountability."
    assert response_eid is not None

    response_event = runtime.eventlog.get_event(int(response_eid))
    claims = (response_event.get("meta") or {}).get("claimed_reflection_ids")
    assert claims == [3, 9]

    # Pending claims are cleared after persistence
    assert runtime.consume_pending_claimed_reflection_ids() is None


def test_reflection_audit_detects_mismatch(tmp_path: Path):
    loop = _make_loop(tmp_path)
    log = loop.eventlog

    response_eid = append_response(
        log,
        content="I just reflected on event #999.",
        meta={"claimed_reflection_ids": [999]},
    )
    reflection_eid = log.append(
        kind="reflection",
        content="Actual reflection content",
        meta={"quality_score": 0.9},
    )

    loop._emit_reflection_audit(tick_no=42)

    audit_events = [ev for ev in log.read_all() if ev["kind"] == "reflection_audit"]
    assert audit_events, "Expected reflection_audit event"
    audit_meta = audit_events[-1]["meta"]

    assert audit_meta["status"] == "mismatch"
    assert audit_meta["claimed_reflection_ids"] == [999]
    assert audit_meta["actual_reflection_ids"] == [int(reflection_eid)]
    assert audit_meta["discrepancy"] == [999]
    assert audit_meta["unclaimed_reflection_ids"] == [int(reflection_eid)]
    assert audit_meta["claimed_source_response_id"] == int(response_eid)


def test_reflection_audit_reports_match(tmp_path: Path):
    loop = _make_loop(tmp_path)
    log = loop.eventlog

    # Append response first so claims reference the upcoming reflection id
    response_eid = append_response(
        log,
        content="Confirmed reflection #2.",
        meta={"claimed_reflection_ids": [2]},
    )
    # Append actual reflection (will have id=2 since response is id=1)
    reflection_eid = log.append(
        kind="reflection",
        content="Reflection with accurate claim",
        meta={"quality_score": 0.85},
    )
    assert int(reflection_eid) == 2

    loop._emit_reflection_audit(tick_no=7)

    audit_events = [ev for ev in log.read_all() if ev["kind"] == "reflection_audit"]
    assert audit_events, "Expected reflection_audit event"
    audit_meta = audit_events[-1]["meta"]

    assert audit_meta["status"] == "match"
    assert audit_meta["claimed_reflection_ids"] == [2]
    assert audit_meta["actual_reflection_ids"] == [2]
    assert audit_meta["discrepancy"] == []
    assert "unclaimed_reflection_ids" not in audit_meta
    assert audit_meta["claimed_source_response_id"] == int(response_eid)
