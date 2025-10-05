# ADR-00X: Embedding Persistence for Recall, Audits, and Acceptance Gating

Status: Proposed (Option A default, Option B automatic via feature detection)

## Context

The clean‑slate PMM appends `embedding_indexed` / `embedding_skipped` events and records only a digest (`meta.digest`) per indexed content event (e.g., `reflection`, `response`). The SQLite event log is hash‑chained and append‑only. We want optional semantic features (recall, audits, future acceptance improvements) while preserving the minimal, deterministic design and keeping dependencies optional.

## Options

### Option A — Status Quo (Events Only)
- Continue emitting `embedding_indexed` / `embedding_skipped` events with a digest only.
- Consumers (recall/audits/acceptance) rely on these events and can recompute vectors on the fly if needed.
- Pros: zero schema change; minimal footprint; preserves ledger simplicity and ordering.
- Cons: no fast semantic search; acceptance can only detect exact duplicates via digest; recomputation cost when needed.

### Option B — Side Table for Embeddings (Recommended; automatic when available)
- Create an auxiliary table (append‑only index) for embeddings and metadata:
  ```sql
  CREATE TABLE IF NOT EXISTS event_embeddings (
    eid INTEGER PRIMARY KEY,
    digest TEXT,
    embedding BLOB,
    summary TEXT,
    keywords TEXT,
    created_at INTEGER
  );
  ```
- Background indexer computes vector/summary/keywords (if enabled), inserts one row, and appends the usual `embedding_indexed` event for auditability.
- Provide a tiny helper `search_semantic(query_vec, k)` using brute‑force cosine/dot over the side table (adequate at current scale).
- Pros: preserves immutable ledger; enables semantic features; optional/opt‑in; can be rebuilt by replaying `embedding_indexed` events.
- Cons: slightly more complexity; ensure side table is never authoritative.

### Option C — Add Columns to Events (Discarded)
- Adding columns (e.g., `embedding BLOB`) to the `events` table conflicts with hash‑chain immutability for background indexing. Computing vectors at insert‑time only would hurt responsiveness and force provider dependencies.

## Decision
- Choose **Option B** with automatic feature detection:
  - At startup, always run the `CREATE TABLE IF NOT EXISTS` statement for the side table.
  - When an embed provider is present (or in test/dummy embed mode), persist embeddings into the side table and still append `embedding_indexed` events to the ledger.
  - When no provider is present, skip persistence silently; the system remains in events-only mode.
  - Consumers (recall/audits/acceptance) detect presence of the side table and non-NULL embeddings automatically; otherwise they fall back to events-only behavior.

## Migration
- At startup, always run the `CREATE TABLE IF NOT EXISTS` statement for the side table.
- No changes to `events` schema; no in‑place updates of historical rows.
- Rebuild path: drop the side table and replay `embedding_indexed` events, or re‑index selectively.

## Performance & Footprint
- Small DBs: brute‑force cosine/dot is acceptable.
- WAL unaffected; side table writes are optional and async.
- Disk can be managed by windowing, reduced precision (e.g., float16), or restricting which kinds are indexed.

## Back‑Compat & Tests
- With no provider present, the DB remains effectively events‑only; all event ordering/tests remain identical.
- With a provider present, ordering is unchanged; we’re only enriching an auxiliary index and still emitting the same `embedding_indexed` events.
- Add tests that validate side‑table writes when a provider (or test/dummy mode) is configured, and graceful fallback otherwise.

## Cross‑References
- Flow and ordering: `docs/flows/reflection.md`
- Injection points: `docs/flows/reflection_injection_points.md`

## Rollout & Guardrails
- Feature is opportunistic and automatic.
- Side table is a cache/index; the event ledger remains the single source of truth.
- Code paths should detect provider/table presence and fall back automatically without user configuration.
