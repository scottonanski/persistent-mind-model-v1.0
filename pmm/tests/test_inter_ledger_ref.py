# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

import tempfile
import os
from pmm.core.event_log import EventLog
from pmm.adapters.dummy_adapter import DummyAdapter
from pmm.runtime.loop import RuntimeLoop


def test_inter_ledger_ref_valid():
    # Setup: create a target ledger with an event at id 47
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        target_path = tmp.name
    target_log = EventLog(target_path)
    target_log.append(kind="test_event", content="target event", meta={})
    # Assume id 1, but to make id 47, append 46 more
    for i in range(46):
        target_log.append(kind="filler", content=f"filler {i}", meta={})
    # Now id 47 exists
    target_events = target_log.read_all()
    assert len(target_events) == 47
    target_event_47 = target_events[-1]
    assert target_event_47["id"] == 47

    # Now, create main ledger
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        main_path = tmp.name
    main_log = EventLog(main_path)
    loop = RuntimeLoop(eventlog=main_log, adapter=DummyAdapter(), autonomy=False)

    # Simulate assistant message with REF: line
    assistant_content = "Some response\nREF: " + target_path + "#47"
    # Manually append assistant_message with REF:
    main_log.append(
        kind="assistant_message", content=assistant_content, meta={"role": "assistant"}
    )

    # Parse REF: lines (simulate run_turn parsing)
    loop._parse_ref_lines(assistant_content)

    # Check for inter_ledger_ref event
    events = main_log.read_all()
    inter_refs = [e for e in events if e["kind"] == "inter_ledger_ref"]
    assert len(inter_refs) == 1
    ref_event = inter_refs[0]
    assert ref_event["content"] == f"REF: {target_path}#47"
    meta = ref_event["meta"]
    assert meta["verified"] is True
    assert meta["target_hash"] == target_event_47["hash"]

    # Cleanup
    os.unlink(target_path)
    os.unlink(main_path)


def test_inter_ledger_ref_invalid():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        invalid_path = tmp.name
    # Invalid path, no event
    main_log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=main_log, adapter=DummyAdapter(), autonomy=False)

    assistant_content = "Response\nREF: " + invalid_path + "#47"
    main_log.append(
        kind="assistant_message", content=assistant_content, meta={"role": "assistant"}
    )
    loop._parse_ref_lines(assistant_content)

    events = main_log.read_all()
    inter_refs = [e for e in events if e["kind"] == "inter_ledger_ref"]
    assert len(inter_refs) == 1
    ref_event = inter_refs[0]
    assert ref_event["content"] == f"REF: {invalid_path}#47"
    meta = ref_event["meta"]
    assert meta["verified"] is False
    assert meta["error"] == "not found"

    # Cleanup
    os.unlink(invalid_path)
