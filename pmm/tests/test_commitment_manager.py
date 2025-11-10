# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

from pmm.core.commitment_manager import CommitmentManager
from pmm.core.event_log import EventLog


def test_open_internal_creates_mc_cid():
    log = EventLog(":memory:")
    manager = CommitmentManager(log)

    cid = manager.open_internal("monitor_rsm", reason="ensure stability")

    assert cid.startswith("mc_")
    events = log.read_all()
    assert len(events) == 1
    event = events[0]
    assert event["kind"] == "commitment_open"
    assert event["meta"]["origin"] == "autonomy_kernel"
    assert event["meta"]["goal"] == "monitor_rsm"
    assert event["meta"]["reason"] == "ensure stability"


def test_open_internal_idempotent_same_goal():
    log = EventLog(":memory:")
    manager = CommitmentManager(log)

    cid_first = manager.open_internal("monitor_rsm")
    cid_second = manager.open_internal("monitor_rsm")

    assert cid_first == cid_second
    events = log.read_all()
    assert len(events) == 1


def test_close_internal_ignores_external():
    log = EventLog(":memory:")
    manager = CommitmentManager(log)

    log.append(
        kind="commitment_open",
        content="External commitment",
        meta={"cid": "user_001", "origin": "assistant"},
    )

    manager.close_internal("user_001", outcome="ignored")

    events = log.read_all()
    close_events = [e for e in events if e["kind"] == "commitment_close"]
    assert close_events == []


def test_get_open_filters_by_origin():
    log = EventLog(":memory:")
    manager = CommitmentManager(log)

    internal_a = manager.open_internal("monitor_rsm")
    log.append(
        kind="commitment_open",
        content="External commitment",
        meta={"cid": "user_001", "origin": "assistant"},
    )
    internal_b = manager.open_internal("review_loops")

    all_open = manager.get_open_commitments()
    assert {e["meta"]["origin"] for e in all_open} == {
        "assistant",
        "autonomy_kernel",
    }

    internal_only = manager.get_open_commitments(origin="autonomy_kernel")
    assert {e["meta"]["cid"] for e in internal_only} == {internal_a, internal_b}
    assert all(e["meta"]["origin"] == "autonomy_kernel" for e in internal_only)

    assert manager.get_open_commitments(origin="user") == []
