"""Read-only HTTP API mirroring probe helpers.

Routes (GET/HEAD only):
  - GET /snapshot
  - GET /directives
  - GET /directives/active
  - GET /commitments/open
  - GET /violations

Each endpoint delegates to functions in `pmm.api.probe` and never writes to the
ledger. It only instantiates `EventLog` to read.

Query parameters:
  - db: optional path to the SQLite DB. Defaults to `.data/pmm.db`.
  - limit/top_k: as supported by the respective probe helper.

Note: We intentionally do NOT set FastAPI response_model on these endpoints to
avoid any filtering or coercion that could change the JSON payload. We return
exactly what the probe helpers return.
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Query, Response

from pmm.api import probe
from pmm.storage.eventlog import EventLog

app = FastAPI(title="PMM Read-only API", version="0.1.0")


def _get_evlog(db: Optional[str]) -> EventLog:
    return EventLog(db) if db else EventLog()


@app.get("/snapshot")
def get_snapshot(
    db: Optional[str] = Query(default=None, description="Path to SQLite DB"),
    limit: int = Query(default=50, ge=1),
    top_k: int = Query(default=5, ge=0, description="Top-K directives to include"),
):
    evlog = _get_evlog(db)
    res = probe.snapshot(evlog, limit=limit)
    res = probe.enrich_snapshot_with_directives(res, evlog, top_k=top_k)
    return res


@app.head("/snapshot")
def head_snapshot(
    db: Optional[str] = Query(default=None, description="Path to SQLite DB"),
    limit: int = Query(default=50, ge=1),
    top_k: int = Query(default=5, ge=0, description="Top-K directives to include"),
):
    # Intentionally avoid any DB work; HEAD should be lightweight.
    return Response(status_code=200)


@app.get("/directives")
def get_directives(
    db: Optional[str] = Query(default=None, description="Path to SQLite DB"),
    limit: Optional[int] = Query(default=None, ge=0),
):
    evlog = _get_evlog(db)
    return probe.snapshot_directives(evlog, limit=limit)


@app.head("/directives")
def head_directives(
    db: Optional[str] = Query(default=None, description="Path to SQLite DB"),
    limit: Optional[int] = Query(default=None, ge=0),
):
    return Response(status_code=200)


@app.get("/directives/active")
def get_directives_active(
    db: Optional[str] = Query(default=None, description="Path to SQLite DB"),
    top_k: Optional[int] = Query(default=None, ge=0),
):
    evlog = _get_evlog(db)
    return probe.snapshot_directives_active(evlog, top_k=top_k)


@app.head("/directives/active")
def head_directives_active(
    db: Optional[str] = Query(default=None, description="Path to SQLite DB"),
    top_k: Optional[int] = Query(default=None, ge=0),
):
    return Response(status_code=200)


@app.get("/commitments/open")
def get_commitments_open(
    db: Optional[str] = Query(default=None, description="Path to SQLite DB"),
    limit: Optional[int] = Query(default=None, ge=0),
):
    evlog = _get_evlog(db)
    return probe.snapshot_commitments_open(evlog, limit=limit)


@app.head("/commitments/open")
def head_commitments_open(
    db: Optional[str] = Query(default=None, description="Path to SQLite DB"),
    limit: Optional[int] = Query(default=None, ge=0),
):
    return Response(status_code=200)


@app.get("/violations")
def get_violations(
    db: Optional[str] = Query(default=None, description="Path to SQLite DB"),
    limit: Optional[int] = Query(default=20, ge=0),
):
    evlog = _get_evlog(db)
    return probe.snapshot_violations(evlog, limit=limit)


@app.head("/violations")
def head_violations(
    db: Optional[str] = Query(default=None, description="Path to SQLite DB"),
    limit: Optional[int] = Query(default=20, ge=0),
):
    return Response(status_code=200)
