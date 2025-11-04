from __future__ import annotations

from pmm_v2.adapters.dummy_adapter import DummyAdapter
from pmm_v2.core.event_log import EventLog
from pmm_v2.runtime.loop import RuntimeLoop


def test_replay_does_not_mutate_ledger(tmp_path):
    db = tmp_path / "log.db"
    log = EventLog(str(db))
    loop = RuntimeLoop(eventlog=log, adapter=DummyAdapter())
    loop.run_turn("hello")
    seq_before = log.hash_sequence()

    # New loop in replay mode on same DB
    log2 = EventLog(str(db))
    loop2 = RuntimeLoop(eventlog=log2, adapter=DummyAdapter(), replay=True)
    events_before = log2.read_all()
    loop2.run_turn("ignored in replay")
    events_after = log2.read_all()
    assert events_before == events_after
    assert seq_before == log2.hash_sequence()

