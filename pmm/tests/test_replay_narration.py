from __future__ import annotations

from pmm.core.event_log import EventLog
from pmm.runtime.replay_narrator import narrate


def test_replay_narration_last_two_lines(tmp_path):
    db = tmp_path / "narr.db"
    log = EventLog(str(db))
    log.append(kind="user_message", content="hi", meta={})
    log.append(kind="assistant_message", content="hello", meta={})
    log.append(
        kind="commitment_open",
        content="Commitment opened: abc",
        meta={"cid": "c1", "text": "abc"},
    )
    log.append(kind="reflection", content="something to say", meta={})

    text = narrate(log, limit=2)
    lines = text.splitlines()
    assert len(lines) == 2
    # Should narrate the last two events
    assert "reflection |" in text
    assert "commitment_open |" in text


def test_replay_narration_marks_unverified_inter_ledger_refs(tmp_path):
    db = tmp_path / "narr2.db"
    log = EventLog(str(db))
    # Two failed refs
    log.append(
        kind="inter_ledger_ref",
        content="REF: ../other_pmm.db#47",
        meta={"verified": False},
    )
    log.append(
        kind="inter_ledger_ref",
        content="REF: ../other_pmm.db#47",
        meta={"verified": False},
    )

    text = narrate(log, limit=10)
    assert "(unverified ref: REF: ../other_pmm.db#47 - create dummy for test)" in text
    # Should appear twice
    assert (
        text.count("(unverified ref: REF: ../other_pmm.db#47 - create dummy for test)")
        == 2
    )
