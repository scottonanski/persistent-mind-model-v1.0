from pmm.storage.eventlog import EventLog
from pmm.api.probe import snapshot


def test_probe_snapshot_returns_current_state_and_recent_events(tmp_path):
    db = tmp_path / "db.sqlite"
    log = EventLog(str(db))

    # Append events
    log.append(kind="identity_change", content="", meta={"name": "Ava"})
    log.append(
        kind="commitment_open", content="", meta={"cid": "c1", "text": "Ship skeleton"}
    )
    log.append(
        kind="commitment_open", content="", meta={"cid": "c2", "text": "Write tests"}
    )
    log.append(kind="commitment_close", content="", meta={"cid": "c1"})

    snap = snapshot(log, limit=3)

    assert snap["identity"]["name"] == "Ava"
    assert "c1" not in snap["commitments"]["open"]
    assert "c2" in snap["commitments"]["open"]
    assert len(snap["events"]) == 3
    assert snap["events"][-1]["kind"] == "commitment_close"
