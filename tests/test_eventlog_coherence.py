import os
import tempfile

from pmm.storage.eventlog import EventLog


def test_multi_instance_cache_refresh():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")

        log_a = EventLog(path=db_path)
        eid1 = log_a.append(kind="test", content="event1", meta={})
        assert eid1 == 1

        log_b = EventLog(path=db_path)
        tail_initial = log_b.read_tail(limit=5)
        assert tail_initial[0]["id"] == 1

        eid2 = log_a.append(kind="test", content="event2", meta={})
        assert eid2 == 2

        tail_after = log_b.read_tail(limit=5)
        assert [ev["id"] for ev in tail_after] == [1, 2]

        all_events = log_b.read_all()
        assert [ev["id"] for ev in all_events] == [1, 2]
