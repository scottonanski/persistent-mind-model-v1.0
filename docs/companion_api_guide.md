# PMM Companion API Guide

This guide walks through running the Companion API locally and using its endpoints.

## 1. Start the server

From the project root:

```bash
python scripts/run_companion_server.py
```

The server listens on `http://localhost:8001` and exposes Swagger docs at `/docs` (ReDoc at `/redoc`).

> A WebSocket `/stream` endpoint is planned but not yet available. Use the REST endpoints described below for now.

## 2. Core endpoints

| Path | Description |
|------|-------------|
| `GET /snapshot` (alias `/events`) | Latest 50 events, identity, and directives |
| `GET /metrics` | Lightweight IAS/GAS snapshot |
| `GET /consciousness` | Full consciousness model (identity, traits, evolution) |
| `GET /reflections` | Recent reflections (`limit` supported) |
| `GET /commitments` | Commitment events (`status=open` for the active set) |
| `POST /events/sql` | Read-only SQL against the `events` table |

All endpoints accept `?db=path/to/database.db` if you want to target a different ledger.

### Example: fetch a snapshot

```bash
curl -s http://localhost:8001/snapshot | jq '.events | length'
```

### Example: metrics health check

```bash
curl -s http://localhost:8001/metrics | jq '.metrics.stage'
```

### Example: latest reflections

```bash
curl -s "http://localhost:8001/reflections?limit=5" | jq '.reflections[] | {id, ts}'
```

### Example: SQL aggregation

```bash
curl -s -X POST http://localhost:8001/events/sql \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT kind, COUNT(*) AS n FROM events GROUP BY kind ORDER BY n DESC"}'
```

## 3. Targeting seeded databases

The repository ships with sample ledgers under `tests/data/`:

- `tests/data/reflections_and_identity.db`
- `tests/data/commitments_projects.db`
- `tests/data/stage_transitions.db`

Pass the path via `?db=` when calling the API:

```bash
curl -s "http://localhost:8001/consciousness?db=tests/data/stage_transitions.db" | jq '.consciousness.identity.stage'
```

## 4. Companion UI integration

Run the Next.js dashboard from `ui/` while the API is active:

```bash
cd ui
npm install
npm run dev
```

The UI fetches data from `http://localhost:8001` by default. Use the database selector in the header to switch between ledgers.

## 5. Production notes

- Use `/metrics` as the primary health check.
- Reverse proxies should forward requests to `http://localhost:8001` and allow long-polling; no WebSockets are required yet.
- For multi-tenant deployments, run separate API processes per ledger to avoid database contention.

For detailed schema information, see the [API reference](guide/api-reference.md).
