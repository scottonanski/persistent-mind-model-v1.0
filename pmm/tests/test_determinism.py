# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

from pmm.adapters.dummy_adapter import DummyAdapter
from pmm.core.event_log import EventLog
from pmm.runtime.loop import RuntimeLoop


def run_loop_dummy(db_path: str) -> list[str]:
    log = EventLog(db_path)
    loop = RuntimeLoop(eventlog=log, adapter=DummyAdapter(), replay=True)
    loop.run_turn("hello determinism")
    return log.hash_sequence()


def test_reproducible_ledger(tmp_path):
    seq1 = run_loop_dummy(str(tmp_path / "run1.db"))
    seq2 = run_loop_dummy(str(tmp_path / "run2.db"))
    assert seq1 == seq2
