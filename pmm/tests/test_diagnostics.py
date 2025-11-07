from __future__ import annotations

from pmm.adapters.dummy_adapter import DummyAdapter
from pmm.core.event_log import EventLog
from pmm.runtime.loop import RuntimeLoop


def test_metrics_turn_event_created(tmp_path):
    db = tmp_path / "diag.db"
    log = EventLog(str(db))
    loop = RuntimeLoop(eventlog=log, adapter=DummyAdapter())
    loop.run_turn("hello world")
    events = log.read_all()
    kinds = [e["kind"] for e in events]
    assert "metrics_turn" in kinds
    diag = [e for e in events if e["kind"] == "metrics_turn"][0]
    assert "provider:" in diag["content"]
    assert "in_tokens:" in diag["content"]
    assert "out_tokens:" in diag["content"]
    assert "lat_ms:" in diag["content"]


def test_diag_cli_output_prints_five(tmp_path, capsys):
    db = tmp_path / "diag2.db"
    log = EventLog(str(db))
    loop = RuntimeLoop(eventlog=log, adapter=DummyAdapter())
    for i in range(7):
        loop.run_turn(f"hi {i}")
    # Simulate CLI --diag printing last 5
    events = [e for e in log.read_tail(100) if e.get("kind") == "metrics_turn"][-5:]
    for e in events:
        print(f"[{e['id']}] metrics_turn | {e['content']}")
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 5
    assert all("metrics_turn |" in ln for ln in out)
