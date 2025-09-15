from __future__ import annotations
import tempfile
import os

from pmm.storage.eventlog import EventLog
from pmm.runtime.planning import maybe_append_planning_thought
from pmm.llm.limits import RATE_LIMITED


def _tmpdb():
    fd, path = tempfile.mkstemp(prefix="pmm_plan_", suffix=".db")
    os.close(fd)
    return path


def _mk(kind, meta=None, content=""):
    return {"kind": kind, "content": content, "meta": (meta or {})}


def test_emits_once_after_reflection():
    db = _tmpdb()
    log = EventLog(db)

    # Seed a reflection event
    rid = log.append("reflection", "A brief reflection.", {"source": "test"})
    rid = int(rid)

    # Chat stub returns a short plan string
    def chat_stub(prompt: str) -> str:
        return "• Clarify in one line.\n• Keep reply under 2 sentences.\n• Ask one precise follow-up."

    eid1 = maybe_append_planning_thought(
        log, chat_stub, from_reflection_id=rid, stage="S1", tick=1
    )
    assert isinstance(eid1, int) and eid1 > 0

    # Calling again should be idempotent (same reflection id)
    eid2 = maybe_append_planning_thought(
        log, chat_stub, from_reflection_id=rid, stage="S1", tick=2
    )
    assert eid2 == eid1

    evs = list(log.read_all())
    plans = [e for e in evs if e["kind"] == "planning_thought"]
    assert len(plans) == 1
    assert plans[0]["meta"]["from_event"] == rid
    assert isinstance(plans[0]["content"], str) and len(plans[0]["content"]) > 0


def test_stage_gate_s0_blocked():
    db = _tmpdb()
    log = EventLog(db)

    rid = log.append("reflection", "R.", {"source": "test"})

    # Any chat; stage gate prevents emission
    def chat_stub(_: str) -> str:
        return "Plan"

    out = maybe_append_planning_thought(
        log, chat_stub, from_reflection_id=int(rid), stage="S0", tick=1
    )
    assert out is None
    evs = list(log.read_all())
    plans = [e for e in evs if e["kind"] == "planning_thought"]
    assert len(plans) == 0


def test_respects_rate_limit_no_emit():
    db = _tmpdb()
    log = EventLog(db)

    rid = log.append("reflection", "R.", {"source": "test"})

    # Chat stub that simulates rate limit sentinel
    def rl_stub(_: str):
        return RATE_LIMITED

    out = maybe_append_planning_thought(
        log, rl_stub, from_reflection_id=int(rid), stage="S2", tick=1
    )
    assert out is None
    evs = list(log.read_all())
    plans = [e for e in evs if e["kind"] == "planning_thought"]
    assert len(plans) == 0


def test_no_bandit_events_from_planning():
    db = _tmpdb()
    log = EventLog(db)

    rid = log.append("reflection", "R.", {"source": "test"})

    def chat_stub(_: str) -> str:
        return "Plan"

    _ = maybe_append_planning_thought(
        log, chat_stub, from_reflection_id=int(rid), stage="S3", tick=1
    )
    evs = list(log.read_all())
    assert all(
        e["kind"] not in {"bandit_guidance_bias", "bandit_arm_chosen"} for e in evs
    )
