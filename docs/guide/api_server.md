# Read-only API (Step 14)

Start the server:
```bash
python -m uvicorn pmm.api.server:app --port 8000 --reload
```

Examples (against a local DB):
```bash
curl -s "http://127.0.0.1:8000/snapshot?db=.data/pmm.db" | head
curl -i "http://127.0.0.1:8000/directives?db=.data/pmm.db"
curl -i "http://127.0.0.1:8000/directives/active?db=.data/pmm.db"
curl -i "http://127.0.0.1:8000/violations?db=.data/pmm.db"
```

Contract:
Only GET/HEAD supported. Mutating verbs (POST/PUT/PATCH/DELETE) → 405.
Payloads mirror pmm/api/probe.py helpers exactly, no writes.
