# 🔌 PMM API Integration Guide

**Connect to PMM programmatically: Monitor the self-model, extract data, and build integrations.**

---

## 🚀 Quick Start Integration

### 1. Start PMM's API Server

```bash
# From PMM directory
python scripts/run_companion_server.py

# Server runs on http://localhost:8001
# API docs at http://localhost:8001/docs
```

### 2. Test Basic Connectivity

```bash
# Check server health
curl http://localhost:8001/metrics

# Sample response (values vary):
{
  "version": "1.0.0",
  "metrics": {
    "ias": 0.12,
    "gas": 0.08,
    "traits": {
      "openness": 0.55,
      "conscientiousness": 0.48,
      "extraversion": 0.42,
      "agreeableness": 0.51,
      "neuroticism": 0.39
    },
    "stage": {"current": "S0"},
    "last_updated": "2024-03-01T12:00:00Z"
  }
}
```

### 3. Get Consciousness State

```bash
curl http://localhost:8001/consciousness
```

---

## 📊 API Endpoints Overview

| Endpoint | Method | Purpose | Notes |
|----------|--------|---------|-------|
| `/snapshot` (alias `/events`) | GET | Latest events + identity snapshot | Returns the most recent 50 events in ascending order |
| `/metrics` | GET | IAS/GAS + stage metadata | Lightweight health probe |
| `/consciousness` | GET | Detailed consciousness state | Includes evolution metrics and latest reflection |
| `/reflections` | GET | Recent reflections | Limit parameter supported (`?limit=20`) |
| `/commitments` | GET | Commitment events | Filter by status with `?status=open` |
| `/events/sql` | POST | Read-only SQL against the ledger | Accepts `SELECT` queries only |

---

## 🧠 Consciousness Monitoring

### Get Full Consciousness State

```bash
curl -s "http://localhost:8001/consciousness?db=.data/pmm.db" | jq .
```

**Response Structure:**
```json
{
  "version": "1.0.0",
  "consciousness": {
    "identity": {
      "name": "PMM",
      "stage": "S0",
      "stage_progress": 0.0,
      "birth_timestamp": "2024-03-01T00:00:00Z",
      "days_alive": 0
    },
    "vital_signs": {
      "ias": 0.12,
      "gas": 0.08,
      "autonomy_level": 0.10,
      "self_awareness": 0.04
    },
    "personality": {
      "traits": {
        "openness": 0.58,
        "conscientiousness": 0.47,
        "extraversion": 0.42,
        "agreeableness": 0.51,
        "neuroticism": 0.39
      }
    },
    "evolution_metrics": {
      "total_events": 52,
      "reflection_count": 3,
      "commitment_count": 1,
      "stage_reached": "S0"
    },
    "latest_insight": {
      "content": "I've noticed increased effectiveness...",
      "timestamp": "2024-01-01T12:00:00Z",
      "kind": "reflection"
    }
  }
}
```

### Monitor Consciousness Health

```python
import requests
import time

def monitor_consciousness():
    while True:
        try:
            response = requests.get('http://localhost:8001/consciousness')
            data = response.json()

            consciousness = data['consciousness']

            # Check autonomy health
            autonomy = consciousness['vital_signs']['autonomy_level']
            awareness = consciousness['consciousness_state']['is_self_aware']

            if autonomy < 0.7:
                print(f"⚠️  Low autonomy detected: {autonomy}")
            if not awareness:
                print("⚠️  Self-awareness issues detected")

            print(f"✅ PMM Stage: {consciousness['identity']['stage']}")
            print(f"📊 IAS: {consciousness['vital_signs']['ias']:.2f}")

        except Exception as e:
            print(f"❌ Connection error: {e}")

        time.sleep(60)  # Check every minute

monitor_consciousness()
```

---

## 📝 Event Log Integration

### Retrieve the latest events

```bash
# Returns identity, directives, and the newest 50 events
curl -s http://localhost:8001/snapshot | jq '.events'
```

Filter client-side for the shapes you need:

```python
import requests
from collections import Counter

resp = requests.get('http://localhost:8001/snapshot')
resp.raise_for_status()
events = resp.json()['events']

distribution = Counter(event['kind'] for event in events)
for kind, count in distribution.most_common():
    print(f"{kind:20} {count}")
```

### Advanced filtering via SQL

Use the read-only SQL endpoint for targeted analysis:

```bash
curl -s -X POST http://localhost:8001/events/sql \
  -H "Content-Type: application/json" \
  -d '{
        "query": "SELECT kind, COUNT(*) AS count FROM events GROUP BY kind ORDER BY count DESC",
        "limit": 100
      }' | jq
```

Only `SELECT` queries are allowed. The response contains column names and row data, making it easy to marshal into DataFrames.

---

## 🧠 Reflection Integration

### Get Recent Reflections

```bash
# Get last 10 reflections
curl "http://localhost:8001/reflections?limit=10"
```

### Self-Improvement Insights

```python
def extract_insights():
    response = requests.get('http://localhost:8001/reflections?limit=50')
    reflections = response.json()['reflections']

    insights = []
    for reflection in reflections:
        content = reflection['content'].lower()

        # Look for self-awareness patterns
        if any(keyword in content for keyword in ['improve', 'better', 'learn', 'adapt']):
            insights.append({
                'timestamp': reflection['ts'],
                'insight': reflection['content'][:200] + '...',
                'type': 'self_improvement'
            })

        # Look for pattern recognition
        elif any(keyword in content for keyword in ['pattern', 'notice', 'trend', 'consistent']):
            insights.append({
                'timestamp': reflection['ts'],
                'insight': reflection['content'][:200] + '...',
                'type': 'pattern_recognition'
            })

    return insights

insights = extract_insights()
for insight in insights[:5]:
    print(f"{insight['timestamp']}: {insight['insight']}")
```

---

## 🎯 Commitment Tracking

### Monitor Active Goals

```bash
# Get all commitments
curl "http://localhost:8001/commitments"

# Get open commitments
curl "http://localhost:8001/commitments?status=open"
```

### Goal Achievement Dashboard

```python
def commitment_dashboard():
    response = requests.get('http://localhost:8001/commitments')
    commitments = response.json()['commitments']

    active = [c for c in commitments if c['kind'] == 'commitment_open']
    completed = [c for c in commitments if c['kind'] == 'commitment_close']
    expired = [c for c in commitments if c['kind'] == 'commitment_expire']

    print("🎯 PMM Commitment Dashboard")
    print(f"📋 Active Goals: {len(active)}")
    print(f"✅ Completed: {len(completed)}")
    print(f"⏰ Expired: {len(expired)}")
    print(".1f"
    # Show recent active commitments
    print("\n📋 Recent Active Commitments:")
    for commitment in active[-3:]:
        print(f"  • {commitment.get('content', 'No description')[:60]}...")

commitment_dashboard()
```

---

## 🔧 Practical Integration Examples

### Health Monitoring Dashboard

```python
import requests
import time
from datetime import datetime

class PMMMonitor:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url

    def get_health_status(self):
        """Get overall PMM health metrics"""
        try:
            consciousness = requests.get(f"{self.base_url}/consciousness").json()
            metrics = requests.get(f"{self.base_url}/metrics").json()

            return {
                'stage': consciousness['consciousness']['identity']['stage'],
                'autonomy': consciousness['consciousness']['vital_signs']['autonomy_level'],
                'self_aware': consciousness['consciousness']['consciousness_state']['is_self_aware'],
                'ias': metrics['metrics']['ias'],
                'gas': metrics['metrics']['gas'],
                'last_update': metrics['metrics']['last_updated']
            }
        except Exception as e:
            return {'error': str(e)}

    def monitor_continuous(self, interval_seconds=300):
        """Monitor PMM health continuously"""
        print("🤖 PMM Health Monitor Started")
        print("=" * 50)

        while True:
            status = self.get_health_status()

            if 'error' in status:
                print(f"❌ Connection Error: {status['error']}")
            else:
                timestamp = datetime.now().strftime('%H:%M:%S')
                autonomy_indicator = "🟢" if status['autonomy'] > 0.7 else "🟡" if status['autonomy'] > 0.4 else "🔴"
                awareness_indicator = "🧠" if status['self_aware'] else "🤖"

                print(f"[{timestamp}] Stage: {status['stage']} | {autonomy_indicator} Autonomy: {status['autonomy']:.2f} | {awareness_indicator} | IAS: {status['ias']:.2f}")

            time.sleep(interval_seconds)

# Usage
monitor = PMMMonitor()
monitor.monitor_continuous()
```

### Data Export Tool

```python
import requests
import json
import csv
from datetime import datetime

class PMMDataExporter:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url

    def export_conversation_history(self, filename=None):
        """Export complete conversation history"""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"pmm_conversation_{timestamp}.json"

        response = requests.get(f"{self.base_url}/events?limit=10000")
        events = response.json()['events']

        # Filter to conversation events
        conversations = [
            event for event in events
            if event['kind'] in ['user_message', 'response']
        ]

        with open(filename, 'w') as f:
            json.dump({
                'export_timestamp': datetime.now().isoformat(),
                'total_conversations': len(conversations),
                'conversations': conversations
            }, f, indent=2)

        print(f"📄 Exported {len(conversations)} conversation events to {filename}")
        return filename

    def export_reflection_insights(self, filename=None):
        """Export PMM's self-reflection insights"""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"pmm_reflections_{timestamp}.csv"

        response = requests.get(f"{self.base_url}/reflections?limit=1000")
        reflections = response.json()['reflections']

        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'kind', 'content_length', 'content_preview'])

            for reflection in reflections:
                content = reflection['content']
                writer.writerow([
                    reflection['ts'],
                    reflection['kind'],
                    len(content),
                    content[:100] + '...' if len(content) > 100 else content
                ])

        print(f"🧠 Exported {len(reflections)} reflections to {filename}")
        return filename

# Usage
exporter = PMMDataExporter()
exporter.export_conversation_history()
exporter.export_reflection_insights()
```

---

## 🌐 Web Integration

### React Hook for PMM Data

```typescript
import { useState, useEffect } from 'react';

interface PMMData {
  consciousness: any;
  metrics: any;
  events: any[];
}

export function usePMM(baseUrl = 'http://localhost:8001') {
  const [data, setData] = useState<PMMData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [consciousnessRes, metricsRes, eventsRes] = await Promise.all([
          fetch(`${baseUrl}/consciousness`),
          fetch(`${baseUrl}/metrics`),
          fetch(`${baseUrl}/events?limit=50`)
        ]);

        const consciousness = await consciousnessRes.json();
        const metrics = await metricsRes.json();
        const events = await eventsRes.json();

        setData({
          consciousness: consciousness.consciousness,
          metrics: metrics.metrics,
          events: events.events
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 30000); // Update every 30s

    return () => clearInterval(interval);
  }, [baseUrl]);

  return { data, loading, error };
}
```

### Vue.js Composition API

```javascript
import { ref, onMounted, onUnmounted } from 'vue';

export function usePMM(baseUrl = 'http://localhost:8001') {
  const consciousness = ref(null);
  const metrics = ref(null);
  const events = ref([]);
  const loading = ref(true);
  const error = ref(null);

  let intervalId = null;

  const fetchData = async () => {
    try {
      const [consciousnessRes, metricsRes, eventsRes] = await Promise.all([
        fetch(`${baseUrl}/consciousness`),
        fetch(`${baseUrl}/metrics`),
        fetch(`${baseUrl}/events?limit=50`)
      ]);

      consciousness.value = (await consciousnessRes.json()).consciousness;
      metrics.value = (await metricsRes.json()).metrics;
      events.value = (await eventsRes.json()).events;
      error.value = null;
    } catch (err) {
      error.value = err.message;
    } finally {
      loading.value = false;
    }
  };

  onMounted(() => {
    fetchData();
    intervalId = setInterval(fetchData, 30000);
  });

  onUnmounted(() => {
    if (intervalId) clearInterval(intervalId);
  });

  return {
    consciousness: readonly(consciousness),
    metrics: readonly(metrics),
    events: readonly(events),
    loading: readonly(loading),
    error: readonly(error)
  };
}
```

---

## 🔒 Security & Best Practices

### API Key Authentication (Future)

```bash
# When API keys are implemented
curl -H "Authorization: Bearer YOUR_API_KEY" \
     http://localhost:8001/consciousness
```

### Rate Limiting

```python
import time

class RateLimitedClient:
    def __init__(self, calls_per_minute=60):
        self.calls_per_minute = calls_per_minute
        self.last_calls = []

    def can_make_call(self):
        now = time.time()
        # Remove calls older than 1 minute
        self.last_calls = [t for t in self.last_calls if now - t < 60]

        return len(self.last_calls) < self.calls_per_minute

    def record_call(self):
        self.last_calls.append(time.time())

    def get(self, url):
        if not self.can_make_call():
            raise Exception("Rate limit exceeded")

        response = requests.get(url)
        self.record_call()
        return response
```

### Error Handling

```python
def safe_api_call(endpoint, retries=3):
    """Make API calls with retry logic"""
    for attempt in range(retries):
        try:
            response = requests.get(f"http://localhost:8001/{endpoint}", timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if attempt == retries - 1:
                raise Exception(f"API call failed after {retries} attempts: {e}")
            time.sleep(2 ** attempt)  # Exponential backoff

# Usage
data = safe_api_call('consciousness')
```

---

## 🚀 Production Deployment

### Docker Integration

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY pmm/ ./pmm/
COPY scripts/ ./scripts/

EXPOSE 8001
CMD ["python", "scripts/run_companion_server.py"]
```

### Systemd Service

```ini
[Unit]
Description=PMM Companion API
After=network.target

[Service]
Type=simple
User=pmm
WorkingDirectory=/opt/pmm
ExecStart=/opt/pmm/venv/bin/python scripts/run_companion_server.py
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## 📞 Integration Support

**Need help with integration?**

- **API Documentation**: [OpenAPI Spec](../pmm_companion_openapi.yaml)
- **Example Code**: Check this guide's examples
- **GitHub Issues**: [Report integration issues](../../issues)
- **Community**: [GitHub Discussions](../../discussions)

**Ready to build with PMM?** Start with the consciousness endpoint—it's your window into PMM's current self-model and metrics. 🚀🤖🔌
