import json
import sys
import subprocess

from pmm.storage.eventlog import EventLog


def test_probe_cli_prints_snapshot_json(tmp_path):
    db_path = tmp_path / "events.db"

    # Prepare a temp database with a few events
    log = EventLog(str(db_path))
    log.append(kind="identity_change", content="", meta={"name": "Ava"})
    log.append(kind="commitment_open", content="", meta={"cid": "c1", "text": "Ship skeleton"})
    log.append(kind="commitment_open", content="", meta={"cid": "c2", "text": "Write tests"})
    log.append(kind="commitment_close", content="", meta={"cid": "c1"})

    # Run the CLI with limit=2 using the module path
    cmd = [sys.executable, "-m", "pmm.api.probe", "--db", str(db_path), "--limit", "2"]
    res = subprocess.run(cmd, capture_output=True, text=True)

    assert res.returncode == 0

    # Parse stdout as JSON
    data = json.loads(res.stdout)
    assert isinstance(data, dict)

    # Expected top-level keys
    assert "identity" in data
    assert "commitments" in data
    assert "events" in data

    events = data["events"]
    assert isinstance(events, list)
    assert len(events) <= 2

    # Order should be ascending, newest last. The last event should be commitment_close
    assert events[-1]["kind"] == "commitment_close"
