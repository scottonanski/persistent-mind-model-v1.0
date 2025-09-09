from pathlib import Path

from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model


def test_projection_reconstructs_state_from_events_only(tmp_path):
    db_path = tmp_path / "events.db"
    log = EventLog(str(db_path))

    # Append events: identity_change -> open c1 -> open c2 -> close c1
    log.append(kind="identity_change", content="", meta={"name": "Ava"})
    log.append(
        kind="commitment_open", content="", meta={"cid": "c1", "text": "Ship skeleton"}
    )
    log.append(
        kind="commitment_open", content="", meta={"cid": "c2", "text": "Write tests"}
    )
    log.append(kind="commitment_close", content="", meta={"cid": "c1"})

    # Rebuild model solely from events
    events = log.read_all()
    model = build_self_model(events)

    assert model["identity"]["name"] == "Ava"
    assert "c1" not in model["commitments"]["open"]
    assert "c2" in model["commitments"]["open"]

    # Prove we do not rely on any JSON persistence side channel
    # Use a commonly named file to assert non-existence
    assert not Path(tmp_path / "persistent_self_model.json").exists()
