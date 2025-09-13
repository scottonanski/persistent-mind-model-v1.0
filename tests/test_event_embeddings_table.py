import os
import tempfile
from pmm.storage.eventlog import EventLog


def test_event_embeddings_table_autocreate():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        log = EventLog(path)
        assert log.has_embeddings_index is True
        # Verify table exists in sqlite_master
        cur = log._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='event_embeddings'"
        )
        assert cur.fetchone() is not None
    finally:
        try:
            log.close()
        except Exception:
            pass
        try:
            os.remove(path)
        except Exception:
            pass
