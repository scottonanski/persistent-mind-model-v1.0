# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

from pmm.core.event_log import EventLog
from pmm.core.commitment_manager import CommitmentManager
from pmm.runtime.context_builder import build_context
from pmm.runtime.prompts import SYSTEM_PRIMER
from pmm.adapters.dummy_adapter import DummyAdapter
from pmm.runtime.loop import RuntimeLoop


def test_primer_contains_required_terms():
    assert "deterministic" in SYSTEM_PRIMER
    assert "ledger" in SYSTEM_PRIMER
    assert "Prefer citing concrete ledger event IDs" in SYSTEM_PRIMER


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


def test_context_appends_rsm_section():
    log = EventLog(":memory:")
    log.append(kind="user_message", content="who are you", meta={})
    log.append(
        kind="assistant_message",
        content="Determinism shapes the strategy.",
        meta={},
    )
    for _ in range(4):
        log.append(
            kind="assistant_message",
            content="CLAIM: failed to reason about ethics.",
            meta={"topic": "ethics"},
        )

    context = build_context(log, limit=2)
    assert "Recursive Self-Model:" in context
    assert "- Tendencies: determinism_emphasis (1)" in context
    assert "- Gaps: ethics" in context


def test_context_includes_internal_goals():
    log = EventLog(":memory:")
    manager = CommitmentManager(log)
    cid = manager.open_internal("analyze_knowledge_gaps", reason="gaps=5")

    context = build_context(log, limit=2)
    assert "Internal Goals:" in context
    assert cid in context
    assert "(analyze_knowledge_gaps)" in context
