from __future__ import annotations
import tempfile
import os
from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import AutonomyLoop, Runtime
from pmm.llm.factory import LLMConfig


def _tmpdb():
    fd, path = tempfile.mkstemp(prefix="pmm_s4cad_", suffix=".db")
    os.close(fd)
    return path


def _run_ticks(n=18):
    db = _tmpdb()
    log = EventLog(db)
    rt = Runtime(
        LLMConfig(
            provider="openai",
            model="gpt-4o-mini",
            embed_provider=None,
            embed_model=None,
        ),
        log,
    )
    loop = AutonomyLoop(eventlog=log, cooldown=rt.cooldown, interval_seconds=0.0)
    for _ in range(n):
        loop.tick()
    return log


def _events_since_last_tick_tail(log: EventLog, start_eid: int):
    return [e for e in log.read_all() if e["id"] >= start_eid]


def test_eval_report_every_5_and_summary_after_report():
    log = _run_ticks(20)
    evs = list(log.read_all())
    # All evaluation_report ticks must be multiples of 5
    reports = [e for e in evs if e["kind"] == "evaluation_report"]
    assert reports, "expected at least one evaluation_report"
    for r in reports:
        assert int(r["meta"]["tick"]) % 5 == 0

    # Each evaluation_summary (if present) appears after its report and before next autonomy_tick
    summaries = [e for e in evs if e["kind"] == "evaluation_summary"]
    for s in summaries:
        rid = int(s["meta"]["from_report_id"])
        r = next(e for e in evs if e["id"] == rid)
        assert r["id"] < s["id"], "summary must follow its report"
        # next autonomy_tick bounds the tick tail
        next_tick = next(
            (e for e in evs if e["kind"] == "autonomy_tick" and e["id"] > r["id"]), None
        )
        if next_tick:
            assert (
                s["id"] < next_tick["id"]
            ), "summary must occur before the next autonomy_tick"
