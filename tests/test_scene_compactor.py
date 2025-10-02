from pmm.runtime.scene_compactor import maybe_compact
from pmm.storage.eventlog import EventLog


def _emit_many(log: EventLog, n: int) -> None:
    for i in range(n):
        log.append(kind="response", content=f"Turn {i} content goes here.", meta={})


def test_emits_compact_with_sources(tmp_path):
    db = tmp_path / "scene1.db"
    log = EventLog(str(db))
    _emit_many(log, 105)

    events = log.read_all()
    out = maybe_compact(events, threshold=100)
    assert out is not None
    src = out["source_ids"]
    assert isinstance(src, list) and len(src) >= 100
    # window bounds
    win = out["window"]
    assert win["start"] == src[0]
    assert win["end"] == src[-1]


def test_non_overlapping_or_versioned(tmp_path):
    db = tmp_path / "scene2.db"
    log = EventLog(str(db))
    # First batch
    _emit_many(log, 100)
    events = log.read_all()
    out1 = maybe_compact(events, threshold=100)
    assert out1 is not None
    # Append more events beyond first window
    _emit_many(log, 100)
    events2 = log.read_all()
    out2 = maybe_compact(events2, threshold=100)
    assert out2 is not None
    # Ensure the second window starts after the end of the first
    assert out2["window"]["start"] > out1["window"]["end"]


def test_summary_bounded_length(tmp_path):
    db = tmp_path / "scene3.db"
    log = EventLog(str(db))
    # Create a lot of verbose events
    for i in range(120):
        log.append(
            kind="response",
            content=("This is a very long line " * 20) + str(i),
            meta={},
        )
    events = log.read_all()
    out = maybe_compact(events, threshold=100)
    assert out is not None
    assert len(out["content"]) <= 500
