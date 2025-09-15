from __future__ import annotations
import tempfile
import os
from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import AutonomyLoop, Runtime
from pmm.llm.factory import LLMConfig


def _tmpdb():
    fd, path = tempfile.mkstemp(prefix="pmm_s4cur_", suffix=".db")
    os.close(fd)
    return path


def test_curriculum_update_then_single_policy_update():
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
    # Run enough ticks for evaluator + curriculum rules to trigger deterministically
    for _ in range(25):
        loop.tick()

    evs = list(log.read_all())

    # Find the latest curriculum_update
    proposals = [e for e in evs if e["kind"] == "curriculum_update"]
    assert proposals, "expected at least one curriculum_update"
    p = proposals[-1]

    # There must be exactly one policy_update applying the same component/params after the proposal and before next autonomy_tick
    comp = p["meta"]["proposed"]["component"]
    params = p["meta"]["proposed"]["params"]
    post_tail = [e for e in evs if e["id"] > p["id"]]
    next_tick = next((e for e in post_tail if e["kind"] == "autonomy_tick"), None)
    window = [e for e in post_tail if (not next_tick) or e["id"] < next_tick["id"]]
    applied = [
        e
        for e in window
        if e["kind"] == "policy_update"
        and e["meta"].get("component") == comp
        and e["meta"].get("params") == params
    ]
    assert len(applied) == 1, "policy_update must apply once per proposal window"

    # Ensure idempotency across later ticks (no duplicates with same params after this window)
    later = [
        e for e in evs if e["id"] > (next_tick["id"] if next_tick else applied[0]["id"])
    ]
    dupes = [
        e
        for e in later
        if e["kind"] == "policy_update"
        and e["meta"].get("component") == comp
        and e["meta"].get("params") == params
    ]
    assert not dupes, "no duplicate policy_update with identical params later"
