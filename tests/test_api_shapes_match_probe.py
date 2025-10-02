from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pmm.api import probe
from pmm.api.server import app
from pmm.storage.eventlog import EventLog


def seed_db(evlog: EventLog):
    # A few diverse events to exercise helpers
    evlog.append("identity_adopt", "Ada", {"name": "Ada"})
    evlog.append(
        "autonomy_directive",
        "Be concise and prefer checklists",
        {"source": "reflection", "origin_eid": 1},
    )
    # Open a commitment
    evlog.append(
        "commitment_open",
        "Commitment opened: Write tests for API",
        {"cid": "c1", "text": "Write tests for API", "origin_eid": 2},
    )
    # Evidence then close
    evlog.append(
        "evidence_candidate",
        "Completion: tests written",
        {"cid": "c1", "evidence_type": "done"},
    )
    evlog.append(
        "commitment_close",
        "Commitment closed: Write tests for API",
        {"cid": "c1", "text": "Write tests for API", "origin_eid": 3},
    )
    # Add a violation row
    evlog.append(
        "invariant_violation",
        "Missing evidence before close (test)",
        {
            "code": "commit_close_no_evidence",
            "message": "test",
            "details": {"foo": "bar"},
        },
    )


def test_server_payloads_match_probe(db_tmp_path, request):
    client = TestClient(app)
    evlog = EventLog(str(db_tmp_path))
    seed_db(evlog)

    params = {"db": str(db_tmp_path)}

    # snapshot
    limit = 50
    top_k = 5
    probe_snap = probe.snapshot(evlog, limit=limit)
    probe_snap = probe.enrich_snapshot_with_directives(probe_snap, evlog, top_k=top_k)
    resp = client.get("/snapshot", params={**params, "limit": limit, "top_k": top_k})
    assert resp.status_code == 200
    assert resp.json() == probe_snap

    # directives
    r = client.get("/directives", params=params)
    assert r.status_code == 200
    assert r.json() == probe.snapshot_directives(evlog)

    # directives active
    r = client.get("/directives/active", params=params)
    assert r.status_code == 200
    assert r.json() == probe.snapshot_directives_active(evlog)

    # commitments open
    r = client.get("/commitments/open", params=params)
    assert r.status_code == 200
    assert r.json() == probe.snapshot_commitments_open(evlog)

    # violations
    vio_limit = 10
    r = client.get("/violations", params={**params, "limit": vio_limit})
    assert r.status_code == 200
    assert r.json() == probe.snapshot_violations(evlog, limit=vio_limit)


# --------- Test fixtures ---------


@pytest.fixture()
def db_tmp_path(tmp_path):
    db_path = tmp_path / "pmm_api_test_shapes.db"
    return db_path
