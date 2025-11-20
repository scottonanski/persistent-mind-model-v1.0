# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

import json

from pmm.core.event_log import EventLog
from pmm.runtime.identity_summary import maybe_append_summary


def test_summary_threshold_and_determinism(tmp_path):
    db = tmp_path / "sum9.db"
    log = EventLog(str(db))
    # fewer than 3 reflections: no summary
    log.append(
        kind="reflection",
        content='{"intent":"a","outcome":"b","next":"c"}',
        meta={},
    )
    assert maybe_append_summary(log) is None
    # reach 3 reflections
    log.append(
        kind="reflection",
        content='{"intent":"a","outcome":"b","next":"c"}',
        meta={},
    )
    log.append(
        kind="reflection",
        content='{"intent":"a","outcome":"b","next":"c"}',
        meta={},
    )
    sid = maybe_append_summary(log)
    assert isinstance(sid, int)

    # determinism: reconstruct same prior state and ensure same summary content
    baseline = log.read_all()[:-1]
    log2 = EventLog(str(tmp_path / "sum9_b.db"))
    for e in baseline:
        log2.append(kind=e["kind"], content=e["content"], meta=e["meta"])
    sid2 = maybe_append_summary(log2)
    s1 = [e for e in log.read_all() if e["id"] == sid][0]
    s2 = [e for e in log2.read_all() if e["id"] == sid2][0]
    assert s1["content"] == s2["content"]


def _seed_rsm_trend(
    log: EventLog, *, determinism_count: int, gap_topic: str | None = None
) -> None:
    for _ in range(determinism_count):
        log.append(
            kind="assistant_message",
            content="Determinism emphasis noted.",
            meta={},
        )
    if gap_topic:
        for _ in range(4):
            log.append(
                kind="assistant_message",
                content=f"CLAIM: failed sense-making on {gap_topic}.",
                meta={"topic": gap_topic},
            )


def _append_reflections(log: EventLog, count: int) -> None:
    for _ in range(count):
        log.append(
            kind="reflection",
            content='{"intent":"a","outcome":"b","next":"c"}',
            meta={},
        )


def test_summary_triggers_on_rsm_delta(tmp_path):
    log = EventLog(str(tmp_path / "sum_rsm_delta.db"))
    _seed_rsm_trend(log, determinism_count=1)
    _append_reflections(log, 3)
    baseline = maybe_append_summary(log)
    assert baseline is not None

    _seed_rsm_trend(log, determinism_count=12)
    _append_reflections(log, 3)

    summary_id = maybe_append_summary(log)
    assert summary_id is not None
    summary_event = next(e for e in log.read_all() if e["id"] == summary_id)
    payload = json.loads(summary_event["content"])
    assert payload["rsm_trend"] == "determinism_emphasis +12"
    assert payload.get("rsm_triggered") is True
    assert summary_event["meta"]["rsm_state"]


def test_summary_includes_rsm_trend(tmp_path):
    log = EventLog(str(tmp_path / "sum_rsm_trend.db"))
    _seed_rsm_trend(log, determinism_count=1)
    _append_reflections(log, 3)
    maybe_append_summary(log)

    _seed_rsm_trend(log, determinism_count=2, gap_topic="ethics")
    _append_reflections(log, 3)
    summary_id = maybe_append_summary(log)
    summary_event = next(e for e in log.read_all() if e["id"] == summary_id)
    payload = json.loads(summary_event["content"])
    trend = payload["rsm_trend"]
    assert "determinism_emphasis +2" in trend
    assert "new gap: ethics" in trend


def test_no_summary_if_rsm_stable(tmp_path):
    log = EventLog(str(tmp_path / "sum_rsm_stable.db"))
    _seed_rsm_trend(log, determinism_count=1)
    _append_reflections(log, 3)
    maybe_append_summary(log)

    for _ in range(9):
        log.append(kind="assistant_message", content="filler", meta={})
    _append_reflections(log, 2)

    assert maybe_append_summary(log) is None
