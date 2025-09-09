from pmm.storage.eventlog import EventLog


def test_eventlog_append_and_read(tmp_path):
    db_path = tmp_path / "events.db"
    log = EventLog(str(db_path))

    id1 = log.append(kind="prompt", content="Hello", meta={"a": 1})
    id2 = log.append(kind="response", content="World", meta={"b": True})

    rows = log.read_all()
    assert len(rows) == 2
    assert [r["id"] for r in rows] == [id1, id2]

    assert rows[0]["kind"] == "prompt"
    assert rows[0]["content"] == "Hello"
    assert rows[0]["meta"] == {"a": 1}

    assert rows[1]["kind"] == "response"
    assert rows[1]["content"] == "World"
    assert rows[1]["meta"] == {"b": True}
