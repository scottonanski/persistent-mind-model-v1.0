from __future__ import annotations

from pmm_v2.core.event_log import EventLog
from pmm_v2.runtime.replay_narrator import narrate


def test_replay_narration_last_two_lines(tmp_path):
    db = tmp_path / "narr.db"
    log = EventLog(str(db))
    log.append(kind="user_message", content="hi", meta={})
    log.append(kind="assistant_message", content="hello", meta={})
    log.append(kind="commitment_open", content="Commitment opened: abc", meta={"cid": "c1", "text": "abc"})
    log.append(kind="reflection", content="something to say", meta={})

    text = narrate(log, limit=2)
    lines = text.splitlines()
    assert len(lines) == 2
    # Should narrate the last two events in ascending order (tail returns ordered)
    assert lines[0].startswith("[") and "] reflection |" in lines[0] or "] commitment_open |" in lines[0]
    assert lines[1].startswith("[")

