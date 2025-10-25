# Methods: Reproducibility Protocols (API‑only)

This write‑up shows how to verify identity persistence and metrics determinism using only the Companion API. Commands assume the API is running at http://localhost:8001 and `jq` is available.

## Prerequisites
- Companion API running (e.g., `./start-companion.sh`)
- Background autonomy is enabled by the server (ticks every ~10s)

## M1. Identity Persistence Across Adapters (Provider‑agnostic)
Goal: Show that identity and traits are ledger‑derived and persist if you switch models/providers.

1) Record current identity
```
curl -s 'http://localhost:8001/snapshot' | jq -r '.identity.name'
```
2) Chat via OpenAI adapter (model name starts with `gpt-`)
```
curl -N -X POST 'http://localhost:8001/chat' \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Briefly say hello."}],"model":"gpt-4o-mini","stream":true}' >/dev/null
```
3) Check identity unchanged
```
curl -s 'http://localhost:8001/snapshot' | jq -r '.identity.name'
```
4) Chat via Ollama adapter (any non‑gpt model name, e.g., `llama3:8b`)
```
curl -N -X POST 'http://localhost:8001/chat' \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Another short message."}],"model":"llama3:8b","stream":true}' >/dev/null
```
5) Verify identity persisted across adapters
```
curl -s 'http://localhost:8001/snapshot' | jq -r '.identity.name'
```
Expected: same name each time unless you explicitly adopted a new one. This demonstrates identity is ledger‑derived, not adapter‑dependent.

## M2. IAS/GAS Recompute Strictly From the Ledger
Goal: Show metrics are recomputed deterministically from events and updated when new relevant events appear.

1) Read current metrics and last metrics_update id
```
BASE=$(curl -s 'http://localhost:8001/metrics' | jq '.metrics')
echo "$BASE" | jq '{ias:.ias,gas:.gas}'
LAST=$(curl -s -X POST 'http://localhost:8001/events/sql' \
  -H 'Content-Type: application/json' \
  -d '{"query":"SELECT id FROM events WHERE kind=\"metrics_update\" ORDER BY id DESC LIMIT 1"}')
echo "$LAST" | jq '.results[0].id'
```
2) Wait for an autonomy tick (relevant event kinds include `autonomy_tick`, `reflection`, `commitment_*`)
- Sleep ~15s to allow the background loop to emit a tick, or trigger normal usage via `/chat` (the loop runs regardless).

3) Request metrics again (the server will recompute if newer relevant events exist)
```
NEW=$(curl -s 'http://localhost:8001/metrics' | jq '.metrics')
echo "$NEW" | jq '{ias:.ias,gas:.gas}'
NEWMET=$(curl -s -X POST 'http://localhost:8001/events/sql' \
  -H 'Content-Type: application/json' \
  -d '{"query":"SELECT id FROM events WHERE kind=\"metrics_update\" ORDER BY id DESC LIMIT 1"}')
echo "$NEWMET" | jq '.results[0].id'
```
4) Confirm that either:
- The latest metrics_update id increased (a recompute occurred) and values are consistent, or
- No recompute was needed (no newer relevant events) and values match baseline

Rationale: `/metrics` calls recompute when it detects relevant events after the last metrics_update. This uses only the ledger; no hidden state.

## M3. Stage Inference Reproducibility
Goal: Show that stage is inferred from recent IAS/GAS telemetry with hysteresis.

1) Fetch detailed metrics
```
curl -s 'http://localhost:8001/metrics?detailed=true' | jq '.metrics'
```
2) Repeat after several ticks (≥30s) and confirm stage changes only when IAS/GAS windows cross thresholds with margin (hysteresis).

## M4. Ledger Export (Optional, API‑only)
Goal: Export raw events for offline inspection while keeping verification API‑only.

```
curl -s -X POST 'http://localhost:8001/events/sql' \
  -H 'Content-Type: application/json' \
  -d '{"query":"SELECT id,ts,kind,content,meta FROM events ORDER BY id ASC"}' | jq > events.json
```

Notes
- Hash chain fields (`prev_hash`, `hash`) can be inspected with SQL, e.g., `SELECT id,prev_hash,hash FROM events ORDER BY id ASC LIMIT 5`. Full cryptographic recomputation can be done offline if needed.
- Identity adoption and commitment lifecycle are best observed via event kinds: `identity_adopt`, `commitment_open/close`, `evidence_candidate`.

