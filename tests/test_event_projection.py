from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model


def test_projection_builds_identity_and_open_commitments(tmp_path):
    db_path = tmp_path / "events.db"
    log = EventLog(str(db_path))

    # 1) identity_change
    log.append(kind="identity_change", content="", meta={"name": "Ava"})
    # 2) commitment_open c1
    log.append(
        kind="commitment_open", content="", meta={"cid": "c1", "text": "Ship skeleton"}
    )
    # 3) commitment_open c2
    log.append(
        kind="commitment_open", content="", meta={"cid": "c2", "text": "Write tests"}
    )
    # 4) commitment_close c1
    log.append(kind="commitment_close", content="", meta={"cid": "c1"})

    events = log.read_all()
    model = build_self_model(events)

    assert model["identity"]["name"] == "Ava"
    assert "c1" not in model["commitments"]["open"]
    assert "c2" in model["commitments"]["open"]
    assert model["commitments"]["open"]["c2"]["text"] == "Write tests"
