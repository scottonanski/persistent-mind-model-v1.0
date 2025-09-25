# PMM Companion API Guide

## Overview

The PMM Companion API is a FastAPI-based read-only server that provides comprehensive access to PMM (Persistent Mind Model) data for the Companion UI. It exposes events, metrics, reflections, commitments, and live streaming capabilities.

## Quick Start

### 1. Install Dependencies

```bash
pip install fastapi uvicorn websockets
```

### 2. Start the Server

```bash
python scripts/run_companion_server.py
```

The server will start on `http://localhost:8001` with:
- **API Documentation**: http://localhost:8001/docs (Swagger UI)
- **Alternative Docs**: http://localhost:8001/redoc (ReDoc)
- **WebSocket Endpoint**: ws://localhost:8001/stream

## API Endpoints

### GET /events

Retrieve paginated events from the PMM event log.

**Parameters:**
- `db` (optional): Path to SQLite database file
- `limit` (default: 50): Maximum events to return (1-1000)
- `after_id` (optional): Return events with ID > this value
- `after_ts` (optional): Return events after timestamp (ISO 8601)
- `kind` (optional): Filter by event kind

**Response:**
```json
{
  "version": "1.0.0",
  "events": [
    {
      "id": 1,
      "kind": "identity_adopt",
      "ts": "2025-09-24T20:04:42.637785+00:00",
      "content": "...",
      "meta": {...}
    }
  ],
  "pagination": {
    "limit": 50,
    "count": 25,
    "next_after_id": 25,
    "has_more": true
  },
  "identity": {
    "name": "Assistant"
  }
}
```

### GET /metrics

Get current PMM metrics including IAS, GAS, OCEAN traits, and stage.

**Parameters:**
- `db` (optional): Path to SQLite database file

**Response:**
```json
{
  "version": "1.0.0",
  "metrics": {
    "ias": 0.75,
    "gas": 0.82,
    "traits": {
      "openness": 0.7,
      "conscientiousness": 0.8,
      "extraversion": 0.6,
      "agreeableness": 0.9,
      "neuroticism": 0.3
    },
    "stage": {
      "current": "S1"
    },
    "last_updated": "2025-09-24T21:39:35.123456Z"
  }
}
```

### GET /reflections

Retrieve reflection events from the PMM system.

**Parameters:**
- `db` (optional): Path to SQLite database file
- `limit` (default: 20): Maximum reflections to return (1-500)

**Response:**
```json
{
  "version": "1.0.0",
  "reflections": [
    {
      "id": 15,
      "kind": "reflection",
      "ts": "2025-09-24T20:05:00.000000+00:00",
      "content": "Reflection content...",
      "meta": {...}
    }
  ],
  "count": 3
}
```

### GET /commitments

Retrieve commitments from the PMM system.

**Parameters:**
- `db` (optional): Path to SQLite database file
- `status` (default: "all"): Filter by status ("open", "closed", "all")
- `limit` (default: 50): Maximum commitments to return (1-500)

**Response:**
```json
{
  "version": "1.0.0",
  "commitments": [
    {
      "id": 10,
      "ts": "2025-09-24T20:04:50.000000+00:00",
      "cid": "commit_123",
      "content": "Complete the API implementation",
      "origin_eid": 8
    }
  ],
  "count": 5
}
```

### WebSocket /stream

Live streaming endpoint for real-time updates.

**Connection:** `ws://localhost:8001/stream`

**Parameters:**
- `db` (optional): Path to SQLite database file
- `subscribe` (optional): Event types to subscribe to (comma-separated)

**Message Types:**
- `heartbeat`: Keep-alive messages every 30 seconds
- `event`: New events (future implementation)
- `metrics_update`: Metric changes (future implementation)

## Usage Examples

### Python Client

```python
import requests

# Get recent events
response = requests.get('http://localhost:8001/events?limit=10')
data = response.json()
print(f"Found {len(data['events'])} events")

# Get metrics with specific database
response = requests.get('http://localhost:8001/metrics?db=tests/data/reflections_and_identity.db')
metrics = response.json()['metrics']
print(f"IAS: {metrics['ias']}, GAS: {metrics['gas']}")

# Get open commitments
response = requests.get('http://localhost:8001/commitments?status=open&limit=5')
commitments = response.json()['commitments']
print(f"Open commitments: {len(commitments)}")
```

### JavaScript/TypeScript Client

```typescript
// Fetch events
const eventsResponse = await fetch('http://localhost:8001/events?limit=20');
const eventsData = await eventsResponse.json();
console.log(`Version: ${eventsData.version}`);
console.log(`Events: ${eventsData.events.length}`);

// WebSocket connection
const ws = new WebSocket('ws://localhost:8001/stream');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data.type, data);
};
```

## Seeded Test Databases

The API includes three seeded SQLite databases for testing:

1. **`tests/data/reflections_and_identity.db`**: Contains multiple reflections and identity adoptions
2. **`tests/data/commitments_projects.db`**: Contains commitments grouped into projects  
3. **`tests/data/stage_transitions.db`**: Contains stage transition events

Use these databases by passing the `db` parameter:
```
http://localhost:8001/events?db=tests/data/reflections_and_identity.db
```

## CORS Configuration

The API is configured to allow requests from:
- `http://localhost:3000` (Next.js default)
- `http://localhost:3001` (Alternative dev server)

## Version Compatibility

All API responses include a `version` field set to `"1.0.0"`. This enables the frontend to handle API changes gracefully in future versions.

## Error Handling

The API returns standard HTTP status codes:
- `200`: Success
- `400`: Bad request (invalid parameters)
- `500`: Internal server error

Error responses include a `detail` field with the error message.

## Development Notes

- The API is strictly read-only and never writes to the event log
- All endpoints support optional database path specification
- Pagination uses cursor-based approach with `after_id` parameter
- WebSocket endpoint currently provides heartbeat; live streaming to be implemented in Phase 2
- CORS is enabled for local development servers
