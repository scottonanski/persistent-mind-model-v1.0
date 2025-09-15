from __future__ import annotations
import tempfile
import os
from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import AutonomyLoop, Runtime
from pmm.llm.factory import LLMConfig


def _tmpdb():
    fd, path = tempfile.mkstemp(prefix="pmm_s4doc_", suffix=".db")
    os.close(fd)
    return path


def _run_for_examples():
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
    for _ in range(30):
        loop.tick()
    return list(log.read_all())


def test_shapes_and_ordering_match_docs():
    evs = _run_for_examples()

    # Presence + minimal schema checks
    rep = next(e for e in evs if e["kind"] == "evaluation_report")
    assert "metrics" in rep["meta"] and "tick" in rep["meta"]

    # summary (optional)
    summ = next((e for e in evs if e["kind"] == "evaluation_summary"), None)
    if summ:
        assert "from_report_id" in summ["meta"]

    plan = next((e for e in evs if e["kind"] == "planning_thought"), None)
    if plan:
        assert "from_event" in plan["meta"] and "tick" in plan["meta"]

    cur = next((e for e in evs if e["kind"] == "curriculum_update"), None)
    if cur:
        assert "proposed" in cur["meta"] and "component" in cur["meta"]["proposed"]

    rat = next(
        (
            e
            for e in evs
            if e["kind"] == "trait_update" and e["meta"].get("reason") == "ratchet"
        ),
        None,
    )
    if rat:
        assert isinstance(rat["meta"].get("delta"), dict) and "tick" in rat["meta"]

    # S4 ordering within a tick tail: report → (summary) → curriculum_update → (policy_update) → (ratchet)
    # Constrain to the region around the first evaluation_report: strictly after the
    # preceding autonomy_tick and before the next autonomy_tick, since the report
    # is emitted after autonomy_tick within the same tick.
    rep_idx = next(i for i, e in enumerate(evs) if e["id"] == rep["id"])
    # Find preceding autonomy_tick index
    start_idx = rep_idx
    while start_idx >= 0 and evs[start_idx]["kind"] != "autonomy_tick":
        start_idx -= 1
    # Find following autonomy_tick index (or end of list)
    end_idx = rep_idx + 1
    while end_idx < len(evs) and evs[end_idx]["kind"] != "autonomy_tick":
        end_idx += 1
    tail = evs[(start_idx + 1) : end_idx]

    idx = {k: i for i, k in enumerate([e["kind"] for e in tail])}
    assert "evaluation_report" in idx
    rep_i = min(i for i, e in enumerate(tail) if e["kind"] == "evaluation_report")
    # If present, summary must be after report
    if "evaluation_summary" in idx:
        assert (
            max(i for i, e in enumerate(tail) if e["kind"] == "evaluation_summary")
            > rep_i
        )
    # If present, curriculum_update must be after report
    if "curriculum_update" in idx:
        assert (
            max(i for i, e in enumerate(tail) if e["kind"] == "curriculum_update")
            > rep_i
        )
