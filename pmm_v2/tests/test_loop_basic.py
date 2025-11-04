from __future__ import annotations

from pmm_v2.adapters.dummy_adapter import DummyAdapter
from pmm_v2.core.event_log import EventLog
from pmm_v2.runtime.loop import RuntimeLoop


def test_single_turn_with_commitment_and_reflection():
    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=DummyAdapter())

    events = loop.run_turn("hello world")

    kinds = [e["kind"] for e in events if e["kind"] != "autonomy_rule_table"]
    assert kinds[0] == "user_message"
    assert kinds[1] == "assistant_message"
    assert "commitment_open" in kinds
    assert kinds.count("reflection") >= 1
    assert kinds[-2] == "autonomy_tick"
    assert kinds[-1] == "reflection"
    assert events[-1]["meta"].get("source") == "autonomy_kernel"
    # Ensure commitment_open meta has cid and text
    commit_event = [e for e in events if e["kind"] == "commitment_open"][0]
    meta = commit_event["meta"]
    assert "cid" in meta and meta["cid"]
    assert meta.get("text") == "note this item"
