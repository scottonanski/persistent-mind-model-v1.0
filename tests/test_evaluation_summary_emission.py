from __future__ import annotations
import tempfile
import os

from pmm.storage.eventlog import EventLog
from pmm.runtime.evaluators.report import maybe_emit_evaluation_summary


def _tmpdb():
    fd, path = tempfile.mkstemp(prefix="pmm_evalsum_", suffix=".db")
    os.close(fd)
    return path


def _mk(kind, meta=None, content=""):
    return {"kind": kind, "content": content, "meta": (meta or {})}


def test_summary_emits_once_per_report():
    db = _tmpdb()
    log = EventLog(db)

    # Seed an evaluation_report event
    rid = log.append(
        "evaluation_report",
        "",
        {
            "component": "performance",
            "metrics": {"completion_rate": 1.0},
            "window": 200,
            "tick": 7,
        },
    )
    rid = int(rid)

    def chat_stub(prompt: str) -> str:
        return "Completion steady; acceptance slightly improving; latency stable."

    eid1 = maybe_emit_evaluation_summary(
        log, chat_stub, from_report_id=rid, stage="S1", tick=7
    )
    assert isinstance(eid1, int) and eid1 > 0

    eid2 = maybe_emit_evaluation_summary(
        log, chat_stub, from_report_id=rid, stage="S1", tick=8
    )
    assert eid2 == eid1

    evs = list(log.read_all())
    sums = [e for e in evs if e["kind"] == "evaluation_summary"]
    assert len(sums) == 1
    assert sums[0]["meta"]["from_report_id"] == rid
    assert isinstance(sums[0]["content"], str) and len(sums[0]["content"]) > 0


def test_summary_rate_limit_or_error_is_noop():
    db = _tmpdb()
    log = EventLog(db)

    rid = log.append(
        "evaluation_report",
        "",
        {"component": "performance", "metrics": {}, "window": 200, "tick": 1},
    )

    def err_stub(_: str) -> str:  # raises
        raise RuntimeError("rate limited or error")

    out = maybe_emit_evaluation_summary(
        log, err_stub, from_report_id=int(rid), stage="S2", tick=2
    )
    assert out is None
    evs = list(log.read_all())
    sums = [e for e in evs if e["kind"] == "evaluation_summary"]
    assert len(sums) == 0


def test_summary_function_does_not_emit_bandit_events():
    db = _tmpdb()
    log = EventLog(db)

    rid = log.append(
        "evaluation_report",
        "",
        {"component": "performance", "metrics": {}, "window": 200, "tick": 1},
    )

    def chat_stub(_: str) -> str:
        return "Summary"

    _ = maybe_emit_evaluation_summary(
        log, chat_stub, from_report_id=int(rid), stage="S3", tick=3
    )
    evs = list(log.read_all())
    assert all(
        e["kind"] not in {"bandit_guidance_bias", "bandit_arm_chosen"} for e in evs
    )
