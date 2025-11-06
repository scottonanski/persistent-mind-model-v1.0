from __future__ import annotations

from pmm_v2.core.event_log import EventLog
from pmm_v2.runtime.context_builder import build_context
from pmm_v2.runtime.prompts import SYSTEM_PRIMER
from pmm_v2.adapters.dummy_adapter import DummyAdapter
from pmm_v2.runtime.loop import RuntimeLoop


def test_primer_contains_required_terms():
    assert "deterministic" in SYSTEM_PRIMER
    assert "ledger" in SYSTEM_PRIMER
    assert "No data in ledger." in SYSTEM_PRIMER


def test_context_builder_tail_window(tmp_path):
    db = tmp_path / "ctx.db"
    log = EventLog(str(db))
    for i in range(6):
        log.append(kind="user_message", content=f"u{i}")
        log.append(kind="assistant_message", content=f"a{i}")
    ctx = build_context(log, limit=3)
    lines = ctx.splitlines()
    assert len(lines) <= 6
    assert all(
        line.startswith("user_message") or line.startswith("assistant_message")
        for line in lines
    )


def test_reflection_appended_when_delta(tmp_path):
    # DummyAdapter emits a COMMIT line, creating a delta -> reflection appended by loop
    db = tmp_path / "refl.db"
    log = EventLog(str(db))
    loop = RuntimeLoop(eventlog=log, adapter=DummyAdapter(), autonomy=False)
    loop.run_turn("hello")
    events = log.read_all()
    kinds = [
        e["kind"]
        for e in events
        if e["kind"] not in ("autonomy_rule_table", "autonomy_stimulus", "rsm_update")
    ]
    assert "assistant_message" in kinds
    assert kinds.count("reflection") == 2
    assert kinds[-2] == "commitment_open"
    assert kinds[-1] == "reflection"
    last_reflection = [e for e in events if e["kind"] == "reflection"][-1]
    assert last_reflection["meta"].get("source") is None
