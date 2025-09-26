# 🧩 Extending PMM (Plugin Patterns)

PMM does not expose a formal plugin registry yet, but there are stable extension points you can use today.

## 1. EventLog append listeners

`EventLog.register_append_listener()` lets you react to every new event deterministically.

```python
from pmm.storage.eventlog import EventLog

evlog = EventLog()

messages = []

def on_event(event: dict) -> None:
    if event.get("kind") == "reflection":
        messages.append(event["content"])
        print(f"New reflection #{event['id']} recorded")

# Attach listener (fires synchronously after each append)
evlog.register_append_listener(on_event)
```

Use append listeners for:
- Real-time dashboards
- Custom telemetry forwarding
- Integrating PMM with external systems (Slack, email, etc.)

## 2. Ledger snapshots

`pmm/runtime/snapshot.py` provides the `LedgerSnapshot` dataclass, which bundles commonly accessed projections (identity, commitments, directives). You can call `Runtime._get_snapshot()` or instantiate `LedgerSnapshot` directly in your automation to avoid replaying the entire log on each query.

## 3. Companion API wrappers

If you prefer to keep integrations out of the runtime process, hit the read-only Companion API. It exposes `/snapshot`, `/metrics`, `/reflections`, and `/commitments` endpoints that stay in sync with the event log.

```python
import requests

snapshot = requests.get("http://localhost:8001/snapshot", params={"limit": 100}).json()
print(snapshot["identity"]["name"])
```

## 4. Safeguards

Any extension must keep PMM deterministic:
- Avoid random numbers, wall-clock branching, or non-repeatable side effects.
- If you emit new events, append them via `EventLog.append(...)` so the hash chain stays intact.
- Log the decisions your extension makes; future auditors should be able to replay your logic from the event stream.

When the formal plugin system lands, these patterns will remain the foundation—build on them to stay forward-compatible.
