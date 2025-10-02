import os
import tempfile

from pmm.storage.eventlog import EventLog


def test_side_table_insert_does_not_create_events():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        log = EventLog(path)
        # Count events before
        cur = log._conn.execute("SELECT COUNT(*) FROM events")
        (before_count,) = cur.fetchone()

        # Insert into side table directly (simulating runtime hook)
        ok = log.insert_embedding_row(
            eid=999, digest="x", embedding_blob=b"\x00\x00\x80?"
        )
        assert ok

        # Count events after — must be identical (no ledger writes)
        cur2 = log._conn.execute("SELECT COUNT(*) FROM events")
        (after_count,) = cur2.fetchone()
        assert before_count == after_count
    finally:
        try:
            log.close()
        except Exception:
            pass
        try:
            os.remove(path)
        except Exception:
            pass
