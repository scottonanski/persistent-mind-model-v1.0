# SPDX-License-Identifier: PMM-1.0

from __future__ import annotations

import hashlib

from pmm.core.event_log import EventLog
from pmm.core.enhancements.meta_reflection_engine import MetaReflectionEngine


def _append_turn(log: EventLog, idx: int) -> None:
    commit_text = f"Commitment #{idx}"
    cid = hashlib.sha1(commit_text.encode("utf-8")).hexdigest()[:8]

    log.append(
        kind="user_message",
        content=f"User says {idx}",
        meta={"role": "user"},
    )
    log.append(
        kind="assistant_message",
        content=f"Assistant reply {idx}\nCOMMIT: {commit_text}",
        meta={"role": "assistant"},
    )
    log.append(
        kind="commitment_open",
        content=f"Commitment opened: {commit_text}",
        meta={
            "cid": cid,
            "origin": "assistant",
            "source": "assistant",
            "text": commit_text,
        },
    )
    if idx % 2 == 0:
        log.append(
            kind="commitment_close",
            content=f"Commitment closed: {cid}",
            meta={
                "cid": cid,
                "origin": "assistant",
                "source": "assistant",
            },
        )
    if idx % 3 == 0:
        log.append(
            kind="reflection",
            content=f"Reflection {idx}",
            meta={"source": "user_turn", "about_event": idx},
        )


def _build_synthetic_ledger(count: int) -> EventLog:
    log = EventLog(":memory:")
    for i in range(count):
        _append_turn(log, i)
    return log


def test_meta_summary_structure() -> None:
    log = _build_synthetic_ledger(60)

    summary = MetaReflectionEngine(log).generate()

    assert set(summary.keys()) == {"patterns", "graph_stats", "event_count"}
    assert isinstance(summary["patterns"], list)
    assert isinstance(summary["graph_stats"], dict)
    assert summary["event_count"] == len(log.read_all())


def test_patterns_are_deterministic() -> None:
    log = _build_synthetic_ledger(40)
    engine = MetaReflectionEngine(log)

    first = engine.generate()
    second = engine.generate()

    assert first == second


def test_graph_stats_included() -> None:
    log = _build_synthetic_ledger(10)

    summary = MetaReflectionEngine(log).generate()

    graph_stats = summary["graph_stats"]
    assert graph_stats["nodes"] >= 1
    assert graph_stats["edges"] >= 0
