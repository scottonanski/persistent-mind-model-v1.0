from __future__ import annotations

from typing import List

from fastapi.testclient import TestClient

from pmm.api.server import app
import pytest
from pmm.storage.eventlog import EventLog


client = TestClient(app)


def test_methods_and_verbs(db_tmp_path):
    # Ensure HEAD/GET work and mutating verbs are rejected with 405 across all routes
    routes: List[str] = [
        "/snapshot",
        "/directives",
        "/directives/active",
        "/commitments/open",
        "/violations",
    ]

    params = {"db": str(db_tmp_path)}

    for path in routes:
        r = client.head(path, params=params)
        assert r.status_code == 200
        r = client.get(path, params=params)
        assert r.status_code == 200
        for method in ("post", "put", "patch", "delete"):
            resp = client.request(method, path, params=params)
            assert resp.status_code == 405


# --------- Test fixtures ---------


@pytest.fixture()
def db_tmp_path(tmp_path):
    # Initialize an empty EventLog at a temporary location
    db_path = tmp_path / "pmm_api_test.db"
    # Create DB file by instantiating EventLog
    _ = EventLog(str(db_path))
    return db_path
