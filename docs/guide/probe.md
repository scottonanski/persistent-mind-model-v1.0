# Probe: Read-only state snapshot

The Probe API gives you a read-only view into an agent's state derived from the SQLite event log. It performs no writes and makes no network calls.

## What `snapshot()` returns

`snapshot(eventlog, *, limit=50)` returns a dictionary with:

- identity.name
- commitments.open (built by replaying events via the projection)
- events: the last ≤ `limit` events, in ascending order (newest last)

This preserves the exact, backward-compatible behavior verified in tests.

```python
from pmm.storage.eventlog import EventLog
from pmm.api.probe import snapshot

log = EventLog(".data/pmm.db")
state = snapshot(log, limit=20)
print(state["identity"]["name"])         # e.g., "Ava"
print(list(state["commitments"]["open"]))  # open commitment ids
print(len(state["events"]))                 # <= 20, ascending, newest last
```

## CLI usage (read-only)

You can inspect the snapshot from the command line. Output is pretty-printed JSON.

```bash
python -m pmm.api.probe --db .data/pmm.db --limit 20
```

This strictly reads from the SQLite database and prints to stdout.

## Pagination (forward-only)

For forward pagination, use `snapshot_paged(eventlog, *, limit=50, after_id=None, after_ts=None)`.
It returns the same shape as `snapshot()`, plus a cursor:

- next_after_id: pass this to the next call as `after_id` if more pages remain.

Cursor semantics:

- after_id: returns events with `id > after_id`.
- after_ts: returns events with `ts > after_ts` (ISO-8601 UTC).
- Always ascending order (newest last). `next_after_id` is computed if there are more rows beyond the page.

Example loop with `next_after_id`:

```python
from pmm.storage.eventlog import EventLog
from pmm.api.probe import snapshot_paged

log = EventLog(".data/pmm.db")
after = None
while True:
    page = snapshot_paged(log, limit=100, after_id=after)
    for ev in page["events"]:
        # process event
        pass
    after = page["next_after_id"]
    if after is None:
        break
```

## Optional redaction hook

You can pass a redactor to trim or strip large fields before returning events from the API. Storage remains unchanged (still read-only), and redaction only affects the returned payload.

```python
def redact(e: dict) -> dict:
    # Truncate large content to 2KB and strip meta["blob"] if present
    out = dict(e)
    if isinstance(out.get("content"), str) and len(out["content"]) > 2048:
        out["content"] = out["content"][:2048] + "… (truncated)"
    meta = dict(out.get("meta") or {})
    meta.pop("blob", None)
    out["meta"] = meta
    return out

page = snapshot_paged(log, limit=100, redact=redact)
```

## Guarantees / invariants

- No writes. No network.
- Ordering: ascending (newest last).
- Backward compatible: `snapshot(...)` semantics are unchanged for callers not using pagination or redaction.
