from __future__ import annotations

from pmm_v2.core.event_log import EventLog
from pmm_v2.runtime.identity_summary import maybe_append_summary


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
