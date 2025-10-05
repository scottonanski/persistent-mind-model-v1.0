# 📤 Data Export Guide

Extract conversations, reflections, and metrics from PMM using the Companion API.

## 1. Export the full event log (JSON)

```bash
curl -s "http://localhost:8001/snapshot?limit=1000" > snapshot.json
```

This includes identity, directives, and the latest 1 000 events.

To fetch the entire ledger, read directly from SQLite:

```bash
sqlite3 .data/pmm.db "SELECT * FROM events" > events.csv
```

## 2. Export conversations only

```python
import json
import requests

resp = requests.get("http://localhost:8001/snapshot", params={"limit": 500})
resp.raise_for_status()

data = resp.json()["events"]

conversations = [
    e for e in data if e["kind"] in {"user_message", "response"}
]

with open("conversation_history.json", "w") as fh:
    json.dump(conversations, fh, indent=2)

print(f"Exported {len(conversations)} conversation events")
```

## 3. Export reflections to CSV

```python
import csv
import requests

resp = requests.get("http://localhost:8001/reflections", params={"limit": 500})
resp.raise_for_status()

with open("reflections.csv", "w", newline="") as fh:
    writer = csv.writer(fh)
    writer.writerow(["id", "timestamp", "kind", "content"])
    for event in resp.json()["reflections"]:
        writer.writerow([
            event["id"],
            event["ts"],
            event["kind"],
            event.get("content", "").strip(),
        ])
```

## 4. Export commitments with status

```python
import requests

resp = requests.get("http://localhost:8001/commitments", params={"limit": 200})
resp.raise_for_status()

commitments = resp.json()["commitments"]

by_status = {}
for event in commitments:
    by_status.setdefault(event["kind"], []).append(event)

for kind, rows in by_status.items():
    print(f"{kind}: {len(rows)} events")
```

## Tips

- Use the `db` query parameter to target alternative ledgers (e.g. `tests/data/reflections_and_identity.db`).
- The API returns the latest events first; use the `after_id` parameter for pagination.
- When you need deterministic exports, shut down the CLI to pause the autonomy loop before fetching.
