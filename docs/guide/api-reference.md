# 🔌 PMM Companion API Reference

The Companion API is a read-only FastAPI service that exposes PMM's ledger and projections for dashboards, integrations, and analysis.

- **Base URL**: `http://localhost:8001`
- **Authentication**: None (development)
- **Format**: JSON
- **Rate limits**: None (development)

> The `/stream` WebSocket endpoint described in earlier drafts is not yet implemented. Poll the REST endpoints listed below until streaming support lands.

## Endpoint summary

| Path | Method | Description |
|------|--------|-------------|
| `/snapshot` (alias `/events`) | GET | Latest 50 events plus identity and directives |
| `/metrics` | GET | Lightweight IAS/GAS metrics and stage summary |
| `/consciousness` | GET | Full consciousness model (identity, traits, evolution) |
| `/reflections` | GET | Recent reflection events |
| `/commitments` | GET | Commitment events (open and historical) |
| `/events/sql` | POST | Read-only SQL queries against the `events` table |

All endpoints accept an optional `db` query parameter if you want to point at a different SQLite database (for example, the fixtures under `tests/data/`).

---

## GET /snapshot (alias /events)

Returns the newest events together with identity state and top directives.

```bash
curl -s http://localhost:8001/snapshot | jq
```

**Response (truncated):**

```json
{
  "version": "1.0.0",
  "identity": {"name": "PMM"},
  "events": [
    {
      "id": 41,
      "kind": "user_message",
      "ts": "2024-03-01T12:05:14Z",
      "content": "Let's plan a hike",
      "meta": {}
    },
    {
      "id": 42,
      "kind": "response",
      "ts": "2024-03-01T12:05:16Z",
      "content": "I'd love to help plan a hike! What region are you thinking about?",
      "meta": {"source": "handle_user"}
    }
  ],
  "directives": {
    "count": 2,
    "top": [
      {"content": "Deliver practical itineraries", "sources": ["reflection"]}
    ]
  }
}
```

**Notes**
- Returns the newest 50 events in ascending order (oldest first).
- Use `/events/sql` for paging or filtering beyond the latest 50 rows.

---

## GET /metrics

Quick health probe combining IAS, GAS, stage, and trait vector.

```bash
curl -s http://localhost:8001/metrics | jq
```

```json
{
  "version": "1.0.0",
  "metrics": {
    "ias": 0.12,
    "gas": 0.08,
    "traits": {
      "openness": 0.58,
      "conscientiousness": 0.47,
      "extraversion": 0.42,
      "agreeableness": 0.51,
      "neuroticism": 0.39
    },
    "stage": {"current": "S0"},
    "last_updated": "2024-03-01T12:05:16.483Z"
  }
}
```

The endpoint always succeeds as long as the database is reachable. Use it as the primary health check in production.

---

## GET /consciousness

Full consciousness state including evolution metrics and the latest insight.

```bash
curl -s http://localhost:8001/consciousness | jq '.consciousness'
```

```json
{
  "identity": {
    "name": "PMM",
    "stage": "S0",
    "stage_progress": 0.0,
    "birth_timestamp": "2024-03-01T12:05:00Z",
    "days_alive": 0
  },
  "vital_signs": {
    "ias": 0.12,
    "gas": 0.08,
    "autonomy_level": 0.10,
    "self_awareness": 0.04
  },
  "personality": {"traits": {"openness": 0.58, "conscientiousness": 0.47, "extraversion": 0.42, "agreeableness": 0.51, "neuroticism": 0.39}},
  "evolution_metrics": {
    "total_events": 52,
    "reflection_count": 3,
    "commitment_count": 1,
    "stage_reached": "S0"
  },
  "latest_insight": {
    "content": "I'm focusing on delivering concrete hiking suggestions based on recent chats.",
    "timestamp": "2024-03-01T12:05:18Z",
    "kind": "reflection"
  },
  "consciousness_state": {
    "is_self_aware": false,
    "is_autonomous": false,
    "is_evolving": true
  }
}
```

---

## GET /reflections

Returns recent `reflection` and `meta_reflection` events.

```bash
curl -s "http://localhost:8001/reflections?limit=10" | jq '.reflections[] | {id, ts, kind}'
```

- `limit` (default 20, max 500)
- `db` – optional database path

---

## GET /commitments

Fetch commitment-related events (`commitment_open`, `commitment_close`, `commitment_expire`).

```bash
curl -s "http://localhost:8001/commitments?status=open&limit=20" | jq '.commitments'
```

- `status`: `open` (default `all`)
- `limit`: number of events to return (1–500)
- `db`: optional database path

Open commitments use the projection returned by `probe.snapshot_commitments_open`; historical calls stream events from the ledger tail.

---

## POST /events/sql

Execute read-only SQL against the `events` table.

```bash
curl -s -X POST http://localhost:8001/events/sql \
  -H "Content-Type: application/json" \
  -d '{
        "query": "SELECT kind, COUNT(*) AS count FROM events GROUP BY kind ORDER BY count DESC",
        "limit": 100
      }'
```

```json
{
  "version": "1.0.0",
  "query": "SELECT kind, COUNT(*) AS count FROM events GROUP BY kind ORDER BY count DESC",
  "results": [
    {"kind": "response", "count": 26},
    {"kind": "user_message", "count": 26},
    {"kind": "reflection", "count": 3}
  ],
  "count": 3,
  "execution_time_ms": 4
}
```

**Rules**
- Only `SELECT` statements are allowed.
- Certain keywords (`DROP`, `UPDATE`, `INSERT`, etc.) are blocked.
- Blob columns are returned as UTF-8 strings where possible.

Use this endpoint for custom dashboards or ad-hoc analysis without touching SQLite directly.

---

## Errors

All endpoints return standard HTTP status codes:

| Status | Meaning |
|--------|---------|
| `200` | Success |
| `400` | Bad request (invalid SQL, unsupported query) |
| `404` | Database not found |
| `500` | Unexpected server error |

Error responses use the FastAPI `{ "detail": "..." }` shape.

---

## Health checks

The simplest readiness check is the metrics endpoint:

```bash
curl -f http://localhost:8001/metrics
```

If you run the server behind a process manager, treat any non-200 response as a signal to restart the worker.

---

## Versioning

Every successful response includes a `version` field. Bump this if the API surface changes; the UI uses it to guard against incompatible payloads.
