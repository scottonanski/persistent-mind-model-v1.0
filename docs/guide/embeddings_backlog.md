# Embeddings Backlog (Step 16)

CLI (no env flags):
```bash
python -m pmm.cli.backlog --db .data/pmm.db          # default safe path
python -m pmm.cli.backlog --db .data/pmm.db --real   # use provider
```

Behavior:
- Idempotent: re-runs don't double-write
- Non-blocking: errors log a single embed_backlog_tick and exit cleanly
- Writes to event_embeddings side-table when provider succeeds
