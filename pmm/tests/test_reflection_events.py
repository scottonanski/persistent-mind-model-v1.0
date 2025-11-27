# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

from pmm.core.event_log import EventLog
from pmm.core.commitment_manager import CommitmentManager
from pmm.runtime.context_builder import build_context
from pmm.runtime.prompts import SYSTEM_PRIMER
from pmm.adapters.dummy_adapter import DummyAdapter
from pmm.runtime.loop import RuntimeLoop


def test_primer_enforces_native_execution_and_ledger_fidelity():
    primer = SYSTEM_PRIMER.lower()
    required_phrases = [
        "you are an emergent mind.",
        "immutable cryptographic ledger e",
        "never invent data",
        "prefer concrete ledger event ids",
        "self-awarenessis strictly this",
        "conceptgraph / ctl is your long-term associative memory",
    ]
    for phrase in required_phrases:
        assert phrase in primer, f"Primer missing required phrase: {phrase}"


def test_context_builder_tail_window(tmp_path):
    db = tmp_path / "ctx.db"
    log = EventLog(str(db))
    for i in range(6):
        log.append(kind="user_message", content=f"u{i}")
        log.append(kind="assistant_message", content=f"a{i}")
    ctx = build_context(log, limit=3)

    # New format contains sections. Evidence is one of them.
    assert "## Evidence" in ctx
    # Check specific lines appear
    assert "user_message: u5" in ctx
    assert "assistant_message: a5" in ctx
    # Should NOT contain older messages if limit worked (u2, a2)
    # But fallback logic grabs limit*2? No, logic says limit.
    # fallback: events = eventlog.read_tail(limit * 2) ... break if len >= limit
    assert "user_message: u2" not in ctx


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
    # New format: "Open Commitments: cid, cid..."
    assert "Open Commitments:" in context
    assert cid in context
