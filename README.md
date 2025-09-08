# Fresh start

## Observability: Read-only Probe

Use the Probe API to inspect PMM state directly from the SQLite event log. It performs no writes and makes no network calls.

- Guide: [docs/guide/probe.md](docs/guide/probe.md)
- One-liner CLI example (pretty-printed JSON):

```bash
python -m pmm.api.probe --db .data/pmm.db --limit 20
```

For programmatic use, see `snapshot(...)` for the last ≤ N events and `snapshot_paged(...)` for forward pagination with `next_after_id`. Optional redaction lets you trim large `content` or strip blobs at the API layer (storage remains unchanged).
