# API Reference

FastAPI server: `pmm/api/companion.py:1`
Base URL defaults to `http://localhost:8001` (see `start-companion.sh`).

## Authentication
- None (local dev). Deployments should place a proxy in front for auth/limits.

## Endpoints

- GET `/snapshot` and GET `/events`
  - Returns a comprehensive snapshot: identity, events (latest by default), directives.
  - Query: `db` (optional path to SQLite DB)
  - Shape: `{ version, identity, events, directives, ... }`

- GET `/metrics`
  - Basic metrics by default; `detailed=true` returns a full metrics snapshot (same as CLI `--@metrics`).
  - Query: `db`, `detailed` (bool)
  - Shape (basic): `{ version, metrics: { ias, gas, traits, stage: { current }, last_updated } }`

- GET `/consciousness`
  - Living Identity dashboard payload: identity vitals, personality, evolution metrics, latest insight.
  - Query: `db`
  - Shape: `{ version, consciousness: { identity, vital_signs, personality, evolution_metrics, latest_insight, consciousness_state } }`

- GET `/reflections`
  - Latest reflection and meta_reflection events.
  - Query: `db`, `limit`
  - Shape: `{ version, reflections: [event], count }`

- GET `/commitments`
  - `status=open` returns open commitments; otherwise returns recent commitment_open/close events.
  - Query: `db`, `status`, `limit`
  - Shape: `{ version, commitments: [...], count }`

- GET `/traces`
  - Reasoning trace summaries.
  - Query: `db`, `limit`, `query_filter`
  - Shape: `{ version, traces: [{ id, timestamp, session_id, query, total_nodes_visited, node_type_distribution, high_confidence_count, high_confidence_paths, sampled_count, reasoning_steps, duration_ms }], count }`

- GET `/traces/{session_id}`
  - Detailed trace for a specific session.
  - Query: `db`
  - Shape: `{ version, summary, samples, sample_count }`

- GET `/traces/stats/overview`
  - Aggregate statistics over reasoning traces.
  - Query: `db`
  - Shape: `{ version, stats: { total_traces, total_nodes_visited, avg_nodes_per_trace, avg_duration_ms, node_type_distribution } }`

- POST `/events/sql`
  - Execute read-only SQL (SELECT) against the events table.
  - Query: `db`
  - Body: `{ "query": "SELECT id, ts, kind, content FROM events ORDER BY id DESC LIMIT 5" }`
  - Response: `{ version, query, results: [ { col: value, ... } ], count, execution_time_ms }`

- POST `/chat`
  - Stream chat responses through the persistent Runtime (OpenAI-compatible SSE).
  - Body (ChatRequest): `{ messages: [{role, content}, ...], model?: string, stream?: true, db?: string }`
  - Stream frames: `data: { "choices": [{ "delta": { "content": "..." } }] }` and `data: [DONE]`

- GET `/models`
  - List available models (Ollama installed models + selected OpenAI defaults).
  - Response: `{ version, models: [{ id, name, provider }] }`

## Notes
- The server maintains a singleton Runtime per (db_path, model) pair and runs the autonomy loop.
- `/events` and `/snapshot` are aliases by design; for paging, use `/events/sql` with a SELECT or extend the server.

## Examples

Get snapshot
```
curl -s 'http://localhost:8001/snapshot'
```

Get metrics (detailed)
```
curl -s 'http://localhost:8001/metrics?detailed=true' | jq
```

List reflections (last 5)
```
curl -s 'http://localhost:8001/reflections?limit=5' | jq '.reflections[] | {id,kind,ts}'
```

Open commitments only
```
curl -s 'http://localhost:8001/commitments?status=open&limit=50' | jq
```

Reasoning traces filtered by query text
```
curl -s 'http://localhost:8001/traces?limit=10&query_filter=identity' | jq
```

Run a read-only SQL query
```
curl -s -X POST 'http://localhost:8001/events/sql' \
  -H 'Content-Type: application/json' \
  -d '{"query":"SELECT id, ts, kind FROM events ORDER BY id DESC LIMIT 5"}' | jq
```

Stream chat response (SSE)
```
curl -N -X POST 'http://localhost:8001/chat' \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"What is my current identity and stage?"}],"model":"gpt-4o-mini","stream":true}'
```
