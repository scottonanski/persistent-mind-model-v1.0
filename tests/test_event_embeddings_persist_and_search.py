import os
import tempfile
import struct
from pmm.storage.eventlog import EventLog
from pmm.storage.semantic import search_semantic


def to_blob(vec):
    return struct.pack("<" + "f" * len(vec), *[float(x) for x in vec])


def test_persist_and_search_semantic_bruteforce():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        log = EventLog(path)
        assert log.has_embeddings_index

        # Insert two distinct vectors for eids 101, 102
        v1 = [1.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0]
        ok1 = log.insert_embedding_row(eid=101, digest="d1", embedding_blob=to_blob(v1))
        ok2 = log.insert_embedding_row(eid=102, digest="d2", embedding_blob=to_blob(v2))
        assert ok1 and ok2

        # Query near v1
        res1 = search_semantic(log._conn, [1.0, 0.0, 0.0], k=1)
        assert res1 == [101]

        # Query near v2
        res2 = search_semantic(log._conn, [0.0, 1.0, 0.0], k=1)
        assert res2 == [102]
    finally:
        try:
            log.close()
        except Exception:
            pass
        try:
            os.remove(path)
        except Exception:
            pass
