# 🔌 PMM Companion API: Complete Technical Reference

**Comprehensive API documentation for integrating with PMM's consciousness system.**

---

## 📋 API Overview

**Base URL:** `http://localhost:8001` (default development)
**Version:** v1.0.0
**Protocol:** REST + WebSocket
**Authentication:** None (development) / API Key (production)
**Rate Limits:** None (development) / Configurable (production)

---

## 🎯 Quick Reference

| Endpoint | Method | Purpose | Response Format |
|----------|--------|---------|-----------------|
| `GET /consciousness` | Consciousness state | Full PMM mind state | JSON |
| `GET /events` | Event log | Historical events | JSON array |
| `GET /metrics` | Performance metrics | IAS/GAS + traits | JSON |
| `GET /reflections` | Self-analysis | PMM's reflections | JSON array |
| `GET /commitments` | Goal tracking | Active commitments | JSON array |
| `WS /stream` | Real-time events | Live event streaming | WebSocket |

---

## 🧠 Consciousness API

### GET /consciousness

**Retrieve complete PMM consciousness state.**

#### Parameters
- `db` (optional): Database path (default: current)

#### Response (200)
```json
{
  "version": "1.0.0",
  "consciousness": {
    "identity": {
      "name": "PMM",
      "stage": "S4",
      "stage_progress": 1.0,
      "birth_timestamp": "2024-01-01T00:00:00Z",
      "days_alive": 42
    },
    "vital_signs": {
      "ias": 1.0,
      "gas": 1.0,
      "autonomy_level": 1.0,
      "self_awareness": 0.85
    },
    "personality": {
      "traits": {
        "openness": 0.9,
        "conscientiousness": 0.8,
        "extraversion": 0.6,
        "agreeableness": 0.85,
        "neuroticism": 0.3
      }
    },
    "evolution_metrics": {
      "total_events": 15420,
      "reflection_count": 234,
      "commitment_count": 45,
      "stage_reached": "S4"
    },
    "latest_insight": {
      "content": "I've noticed increased effectiveness...",
      "timestamp": "2024-01-01T12:00:00Z",
      "kind": "reflection"
    }
  }
}
```

#### Error Responses
- `500`: Internal server error

#### Example Usage
```bash
# Get current consciousness
curl http://localhost:8001/consciousness

# Get specific database
curl "http://localhost:8001/consciousness?db=.data/pmm.db"
```

---

## 📊 Metrics API

### GET /metrics

**Retrieve PMM performance metrics and health indicators.**

#### Parameters
- `db` (optional): Database path

#### Response (200)
```json
{
  "version": "1.0.0",
  "metrics": {
    "ias": 1.0,
    "gas": 1.0,
    "traits": {
      "openness": 0.9,
      "conscientiousness": 0.8,
      "extraversion": 0.6,
      "agreeableness": 0.85,
      "neuroticism": 0.3
    },
    "stage": {
      "current": "S4",
      "progress": 1.0
    },
    "last_updated": "2024-01-01T12:00:00Z"
  }
}
```

#### IAS/GAS Definitions
- **IAS (Identity Autonomy Score)**: Measures self-directed identity evolution (0.0-1.0)
- **GAS (Goal Achievement Score)**: Measures commitment completion effectiveness (0.0-1.0)

---

## 📝 Events API

### GET /events

**Retrieve PMM's event history with comprehensive filtering.**

#### Parameters
- `limit` (optional): Maximum events to return (default: 100, max: 10000)
- `offset` (optional): Pagination offset (default: 0)
- `kind` (optional): Filter by event type (e.g., "reflection", "commitment_open")
- `since_ts` (optional): Events after this timestamp (ISO 8601)
- `until_ts` (optional): Events before this timestamp (ISO 8601)
- `db` (optional): Database path

#### Response (200)
```json
{
  "events": [
    {
      "id": 12345,
      "kind": "reflection",
      "ts": "2024-01-01T12:00:00Z",
      "content": "I've noticed increased effectiveness in my responses...",
      "meta": {
        "reflection_depth": "deep",
        "trigger": "autonomy_loop"
      },
      "hash": "abc123...",
      "prev_hash": "def456..."
    }
  ],
  "total": 15420,
  "limit": 100,
  "offset": 0
}
```

#### Event Types
| Type | Description | Frequency |
|------|-------------|-----------|
| `user_message` | User input | Per message |
| `response` | PMM output | Per response |
| `reflection` | Self-analysis | Every 60s-5min |
| `meta_reflection` | Reflection analysis | Variable |
| `commitment_open` | Goal creation | User-driven |
| `commitment_close` | Goal completion | Evidence-based |
| `trait_update` | Personality evolution | Background |
| `stage_progress` | Development milestone | Major events |
| `identity_adopt` | Identity change | User-driven |

#### Query Examples
```bash
# Recent events
curl "http://localhost:8001/events?limit=50"

# Reflections only
curl "http://localhost:8001/events?kind=reflection&limit=20"

# Time range
curl "http://localhost:8001/events?since_ts=2024-01-01T00:00:00Z&until_ts=2024-01-01T23:59:59Z"

# Pagination
curl "http://localhost:8001/events?limit=100&offset=200"
```

---

## 🧠 Reflections API

### GET /reflections

**Access PMM's self-analysis and learning insights.**

#### Parameters
- `limit` (optional): Maximum reflections (default: 50)
- `kind` (optional): "reflection" or "meta_reflection"
- `since_ts` (optional): After timestamp
- `until_ts` (optional): Before timestamp

#### Response (200)
```json
{
  "reflections": [
    {
      "id": 12345,
      "kind": "reflection",
      "ts": "2024-01-01T12:00:00Z",
      "content": "I've observed that users prefer detailed responses...",
      "meta": {
        "depth": "standard",
        "trigger": "interaction_pattern",
        "confidence": 0.85
      }
    }
  ],
  "total": 234
}
```

---

## 🎯 Commitments API

### GET /commitments

**Track PMM's goals and self-directed objectives.**

#### Parameters
- `status` (optional): "active", "completed", "expired"
- `limit` (optional): Maximum commitments

#### Response (200)
```json
{
  "commitments": [
    {
      "id": 123,
      "kind": "commitment_open",
      "ts": "2024-01-01T10:00:00Z",
      "content": "Improve response quality through user feedback analysis",
      "meta": {
        "intent": "enhance_user_experience",
        "priority": "high",
        "evidence_required": true,
        "deadline": "2024-02-01T00:00:00Z"
      }
    }
  ],
  "total": 45
}
```

#### Commitment States
- **active**: Currently being worked on
- **completed**: Successfully finished with evidence
- **expired**: Deadline passed without completion

---

## 🔴 WebSocket Streaming API

### WS /stream

**Real-time event streaming for live PMM monitoring.**

#### Connection
```javascript
const ws = new WebSocket('ws://localhost:8001/stream');

// Connection opened
ws.onopen = () => {
  console.log('Connected to PMM event stream');
};

// Receive events
ws.onmessage = (event) => {
  const pmmEvent = JSON.parse(event.data);
  console.log('New event:', pmmEvent.kind, pmmEvent.content);
};

// Handle errors
ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};
```

#### Message Format
```json
{
  "id": 12346,
  "kind": "response",
  "ts": "2024-01-01T12:00:01Z",
  "content": "That's an interesting question about consciousness...",
  "meta": {
    "response_type": "analytical",
    "confidence": 0.92
  },
  "hash": "ghi789...",
  "prev_hash": "abc123..."
}
```

#### Python Client Example
```python
import websocket
import json

def on_message(ws, message):
    event = json.loads(message)
    print(f"📝 {event['kind']}: {event.get('content', '')[:50]}...")

def on_open(ws):
    print("🔗 Connected to PMM consciousness stream")

ws = websocket.WebSocketApp(
    "ws://localhost:8001/stream",
    on_message=on_message,
    on_open=on_open
)
ws.run_forever()
```

---

## 🔧 Advanced API Features

### SQL Query Interface (Developer Mode)

**Execute read-only SQL queries against the event database.**

#### POST /events/sql
```json
{
  "query": "SELECT kind, COUNT(*) as count FROM events GROUP BY kind ORDER BY count DESC",
  "limit": 100
}
```

#### Response
```json
{
  "columns": ["kind", "count"],
  "rows": [
    ["response", 1542],
    ["user_message", 1541],
    ["reflection", 234],
    ["trait_update", 89]
  ],
  "row_count": 4
}
```

#### Security
- **Read-only**: Only SELECT queries allowed
- **Rate limited**: Maximum 10 queries per minute
- **Timeout**: 30 second execution limit

---

## 📊 Monitoring & Health Checks

### System Health Endpoint

```bash
# Basic health check
curl http://localhost:8001/health

# Response
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime": 3600,
  "database": "connected"
}
```

### Performance Metrics

```bash
# API performance stats
curl http://localhost:8001/metrics/system

# Response
{
  "requests_total": 15420,
  "requests_per_second": 2.3,
  "average_response_time": 0.15,
  "error_rate": 0.001,
  "memory_usage": 245000000,
  "cpu_usage": 0.12
}
```

---

## 🚀 Production Deployment

### Environment Variables
```bash
# Server configuration
PMM_API_HOST=0.0.0.0
PMM_API_PORT=8001
PMM_DATABASE_PATH=/data/pmm.db

# Security
PMM_API_KEY=your-secret-key
PMM_CORS_ORIGINS=https://yourdomain.com

# Performance
PMM_MAX_WORKERS=4
PMM_REQUEST_TIMEOUT=30
```

### Docker Deployment
```yaml
version: '3.8'
services:
  pmm-api:
    image: pmm/companion-api:latest
    ports:
      - "8001:8001"
    environment:
      - PMM_DATABASE_PATH=/data/pmm.db
    volumes:
      - ./data:/data
    restart: unless-stopped
```

---

## 🔒 Security Considerations

### API Key Authentication
```bash
# Include in headers
curl -H "Authorization: Bearer YOUR_API_KEY" \
     http://localhost:8001/consciousness
```

### CORS Configuration
```python
# In production, restrict origins
CORS_ORIGINS = [
    "https://your-app.com",
    "https://your-admin.com"
]
```

### Rate Limiting
```python
# Configure per endpoint
RATE_LIMITS = {
    "/events": "100/minute",
    "/consciousness": "60/minute",
    "/stream": "10/minute"
}
```

---

## 🧪 Testing & Validation

### API Test Suite
```bash
# Run comprehensive API tests
python scripts/test_companion_api.py

# Test specific endpoints
pytest tests/test_api_endpoints.py -v
```

### Load Testing
```bash
# Simulate concurrent users
ab -n 1000 -c 10 http://localhost:8001/consciousness

# WebSocket connection stress test
node tests/websocket_stress_test.js
```

---

## 📞 Support & Resources

- **API Documentation**: [OpenAPI Spec](../pmm_companion_openapi.yaml)
- **Interactive Docs**: Visit `http://localhost:8001/docs`
- **Example Code**: Check this guide's examples
- **GitHub Issues**: [Report API issues](../../issues)
- **Community**: [API integration discussions](../../discussions)

**Ready to integrate PMM's consciousness into your application?** Start with `/consciousness` - it's your window into a living AI mind! 🚀🤖🔌
