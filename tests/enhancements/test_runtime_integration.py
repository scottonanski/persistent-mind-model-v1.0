# SPDX-License-Identifier: PMM-1.0

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pmm.core.commitment_manager import CommitmentManager
from pmm.core.event_log import EventLog
from pmm.core.ledger_metrics import compute_metrics
from pmm.core.mirror import Mirror
from pmm.runtime.reflection_synthesizer import synthesize_reflection


def _append_basic_turn(log: EventLog, text: str) -> None:
    log.append(
        kind="user_message",
        content=f"User input: {text}",
        meta={"role": "user"},
    )
    log.append(
        kind="assistant_message",
        content=f"Assistant output for {text}\nCOMMIT: {text}",
        meta={"role": "assistant"},
    )
    log.append(
        kind="metrics_turn",
        content="provider:dummy,model:fixture,in_tokens:4,out_tokens:4,lat_ms:0",
        meta={},
    )


def _seed_reflection(log: EventLog, text: str) -> int | None:
    _append_basic_turn(log, text)
    return synthesize_reflection(log)


def test_commitment_open_includes_impact_score() -> None:
    log = EventLog(":memory:")
    manager = CommitmentManager(log)

    manager.open_commitment("Test commit")

    events = [e for e in log.read_all() if e["kind"] == "commitment_open"]
    assert events, "Expected a commitment_open event"
    meta = events[-1]["meta"]
    assert "impact_score" in meta
    assert 0.0 <= meta["impact_score"] <= 1.0


def test_reflection_triggers_meta_summary() -> None:
    log = EventLog(":memory:")

    reflection_id = _seed_reflection(log, "alpha task")

    assert reflection_id is not None
    events = log.read_all()
    assert events[-1]["kind"] == "meta_summary"
    payload = json.loads(events[-1]["content"])
    assert "patterns" in payload
    assert "graph_stats" in payload


def test_metrics_include_stability_block(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.db"
    log = EventLog(str(db_path))

    # Two turns to populate ledger with reflection + meta_summary data
    for idx in range(2):
        _seed_reflection(log, f"task-{idx}")
        cid_text = f"Commit {idx}"
        cid = hashlib.sha1(cid_text.encode("utf-8")).hexdigest()[:8]
        log.append(
            kind="commitment_open",
            content=f"Commitment opened: {cid_text}",
            meta={
                "cid": cid,
                "origin": "assistant",
                "source": "assistant",
                "text": cid_text,
                "impact_score": 0.75,
            },
        )
        log.append(
            kind="commitment_close",
            content=f"Commitment closed: {cid}",
            meta={
                "cid": cid,
                "origin": "assistant",
                "source": "assistant",
            },
        )

    metrics = compute_metrics(str(db_path))

    assert "stability" in metrics
    stability = metrics["stability"]
    assert set(stability.keys()) == {
        "commitment_consistency",
        "reflection_coherence",
        "overall_stability",
    }


def test_replay_integrity(tmp_path: Path) -> None:
    db_path = tmp_path / "replay.db"
    log = EventLog(str(db_path))

    for idx in range(3):
        _seed_reflection(log, f"reflection-{idx}")

    first_sequence = log.hash_sequence()

    # Reload and rebuild projections to ensure determinism holds
    reloaded = EventLog(str(db_path))
    Mirror(reloaded, enable_rsm=True, listen=False)
    second_sequence = reloaded.hash_sequence()

    assert first_sequence == second_sequence
    assert reloaded.read_all()[-1]["kind"] == "meta_summary"
