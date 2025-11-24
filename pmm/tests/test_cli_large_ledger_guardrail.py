# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

from pmm.core.event_log import EventLog
from pmm.runtime.cli import handle_graph_command, _handle_checkpoint


def test_graph_command_guardrails_on_large_ledger() -> None:
    log = EventLog(":memory:")
    # Simulate large ledger by setting high id via dummy events
    for _ in range(100_001):
        log.append(kind="test_event", content="x", meta={})

    res = handle_graph_command("/graph stats", log)
    assert (
        res
        == "Graph stats disabled on large ledgers; use checkpoints or filtered tools."
    )


def test_checkpoint_guardrail_on_large_ledger() -> None:
    log = EventLog(":memory:")
    # Populate >100000 events to trigger guardrail
    for _ in range(100_001):
        log.append(kind="test_event", content="x", meta={})
    # add a summary_update to anchor
    log.append(kind="summary_update", content="s", meta={})

    res = _handle_checkpoint(log)
    assert (
        res
        == "Checkpoint creation blocked: ledger too large for unbounded hash. Use segmented checkpoints."
    )
