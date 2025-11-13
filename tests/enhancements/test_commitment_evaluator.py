# SPDX-License-Identifier: PMM-1.0

from __future__ import annotations

import hashlib

import pytest

from pmm.core.event_log import EventLog
from pmm.core.enhancements.commitment_evaluator import CommitmentEvaluator


def _append_commitment_open(log: EventLog, text: str, cid: str | None = None) -> str:
    cid = cid or hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    log.append(
        kind="commitment_open",
        content=f"Commitment opened: {text}",
        meta={
            "cid": cid,
            "origin": "assistant",
            "source": "assistant",
            "text": text,
        },
    )
    return cid


def _append_commitment_close(log: EventLog, cid: str) -> None:
    log.append(
        kind="commitment_close",
        content=f"Commitment closed: {cid}",
        meta={
            "cid": cid,
            "origin": "assistant",
            "source": "assistant",
        },
    )


def test_empty_ledger_returns_baseline_score() -> None:
    log = EventLog(":memory:")
    evaluator = CommitmentEvaluator(log)

    score = evaluator.compute_impact_score("test")

    assert score == pytest.approx(0.5)


def test_historical_success_influences_score() -> None:
    log = EventLog(":memory:")
    text = "A"
    cid = _append_commitment_open(log, text)
    _append_commitment_close(log, cid)

    score = CommitmentEvaluator(log).compute_impact_score(text)

    assert score == pytest.approx(1.0)


def test_graph_weight_affects_output() -> None:
    baseline_log = EventLog(":memory:")
    base_text = "Baseline"
    base_cid = _append_commitment_open(baseline_log, base_text)
    _append_commitment_close(baseline_log, base_cid)
    baseline_score = CommitmentEvaluator(baseline_log).compute_impact_score(base_text)

    weighted_log = EventLog(":memory:")
    weighted_text = "Weighted"
    weighted_log.append(
        kind="user_message",
        content="User context",
        meta={"role": "user"},
    )
    weighted_log.append(
        kind="assistant_message",
        content=f"Assistant reply\nCOMMIT: {weighted_text}",
        meta={"role": "assistant"},
    )
    weighted_cid = _append_commitment_open(weighted_log, weighted_text)
    _append_commitment_close(weighted_log, weighted_cid)

    weighted_score = CommitmentEvaluator(weighted_log).compute_impact_score(
        weighted_text
    )

    assert weighted_score < baseline_score
    assert 0.0 <= weighted_score <= 1.0


def test_deterministic_replay() -> None:
    log = EventLog(":memory:")
    texts = ["one", "two", "three"]
    for text in texts:
        cid = _append_commitment_open(log, text)
        if text != "two":
            _append_commitment_close(log, cid)

    evaluator = CommitmentEvaluator(log)

    first = evaluator.compute_impact_score("two")
    second = evaluator.compute_impact_score("two")

    assert first == pytest.approx(second)
