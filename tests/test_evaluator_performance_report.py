from __future__ import annotations

import itertools
import os
import tempfile

from pmm.runtime.evaluators.performance import (
    METRICS_WINDOW,
    compute_performance_metrics,
    emit_evaluation_report,
)
from pmm.storage.eventlog import EventLog


def _tmpdb():
    fd, path = tempfile.mkstemp(prefix="pmm_eval_", suffix=".db")
    os.close(fd)
    return path


def _mk(kind, meta=None, content=""):
    return {"kind": kind, "content": content, "meta": (meta or {})}


def test_metrics_deterministic_and_order_insensitive():
    # Craft an equivalent multiset of events in different orders
    base = [
        _mk("commitment_open"),
        _mk("commitment_close"),
        _mk("commitment_expire"),
        _mk("bandit_reward", {"reward": 1.0}),
        _mk("bandit_reward", {"reward": 0.0}),
        _mk("llm_latency", {"op": "chat", "ms": 100}),
        _mk("llm_latency", {"op": "chat", "ms": 200}),
        _mk("audit_report", {"category": "novelty_trend", "value": "same"}),
        _mk("audit_report", {"category": "novelty_trend", "value": "up"}),
    ]
    a = list(base)
    b = list(reversed(base))
    c = list(itertools.chain(base[3:], base[:3]))  # rotate

    m_a = compute_performance_metrics(a, window=METRICS_WINDOW)
    m_b = compute_performance_metrics(b, window=METRICS_WINDOW)
    m_c = compute_performance_metrics(c, window=METRICS_WINDOW)

    # All metrics must match across permutations
    assert m_a == m_b == m_c
    # Sanity: expected values from 'base'
    # opens=1, closes=1, expires=1 => eligible = max(0, 1-1)=0 → denom fallback = opens=1 → 1/1
    assert m_a["completion_rate"] == 1.0
    # bandit_accept_winrate = 1 positive out of 2
    assert m_a["bandit_accept_winrate"] == 0.5
    # llm mean = (100+200)/2
    assert m_a["llm_chat_latency_mean_ms"] == 150.0
    # novelty_same_ratio = 1 same out of 2 reports
    assert m_a["novelty_same_ratio"] == 0.5


def test_single_emission_per_tick():
    db = _tmpdb()
    log = EventLog(db)

    # Seed a few noise events
    for _ in range(5):
        log.append("debug", "", {})

    tail = log.read_tail(limit=500)
    metrics = compute_performance_metrics(tail, window=METRICS_WINDOW)

    # Emit once
    eid1 = emit_evaluation_report(log, metrics=metrics, tick=7)
    assert isinstance(eid1, int) and eid1 > 0

    # Try to emit again for the same tick → must be idempotent
    eid2 = emit_evaluation_report(log, metrics=metrics, tick=7)
    assert eid2 == eid1

    # Different tick → should emit a new event
    eid3 = emit_evaluation_report(log, metrics=metrics, tick=8)
    assert isinstance(eid3, int) and eid3 != eid1

    # Validate shape
    events = list(log.read_all())
    reports = [e for e in events if e["kind"] == "evaluation_report"]
    assert len(reports) == 2
    for r in reports:
        assert "metrics" in r["meta"]
        assert "tick" in r["meta"]
        assert r["meta"]["component"] == "performance"


def test_windowing_bounds():
    db = _tmpdb()
    log = EventLog(db)

    # Push >window events where early ones would skew metrics if not sliced
    for _ in range(METRICS_WINDOW + 10):
        log.append("bandit_reward", "", {"reward": 1.0})  # all positive in tail
    # Add a couple of negatives; then more positives to ensure negatives fall outside the tail window
    for _ in range(3):
        log.append("bandit_reward", "", {"reward": 0.0})
    # Append enough positives to push the 3 negatives outside the last METRICS_WINDOW events
    # We need at least METRICS_WINDOW additional positives after the negatives
    for _ in range(METRICS_WINDOW):
        log.append("bandit_reward", "", {"reward": 1.0})

    m = compute_performance_metrics(list(log.read_all()), window=METRICS_WINDOW)
    # Expect winrate to be ~1.0 because the last `window` rewards are positive
    assert m["bandit_accept_winrate"] == 1.0
