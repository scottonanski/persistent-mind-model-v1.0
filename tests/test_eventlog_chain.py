from pmm.storage.eventlog import EventLog


def test_chain_valid_across_many_appends(tmp_path):
    db = tmp_path / "chain.db"
    log = EventLog(str(db))
    for i in range(100):
        log.append("debug", f"e{i}", {"i": i})
    assert log.verify_chain() is True


def test_chain_detects_tamper(tmp_path):
    import sqlite3
    db = tmp_path / "chain.db"
    log = EventLog(str(db))
    log.append("debug", "ok", {})
    log.append("debug", "ok2", {})
    assert log.verify_chain() is True
    # Tamper with content of id=2
    conn = sqlite3.connect(str(db))
    conn.execute("UPDATE events SET content='CORRUPTED' WHERE id=2")
    conn.commit(); conn.close()
    assert log.verify_chain() is False


def test_genesis_rule_enforced(tmp_path):
    import sqlite3
    db = tmp_path / "chain.db"
    log = EventLog(str(db))
    # Normal append should create genesis with prev_hash NULL
    log.append("debug", "ok", {})
    # Try to insert a bogus second row with NULL prev_hash -> should fail verify
    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO events(ts, kind, content, meta, prev_hash, hash) VALUES (strftime('%s','now'), 'debug', 'bad', '{}', NULL, 'fake')")
    conn.commit(); conn.close()
    assert log.verify_chain() is False
