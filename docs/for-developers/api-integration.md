# 🔌 PMM API Integration Guide

**Connect to PMM programmatically: Monitor consciousness, extract data, and build integrations.**

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

# Expected response:
{
  "version": "1.0.0",
  "metrics": {
    "ias": 1.0,
    "gas": 1.0,
    "traits": {...},
    "stage": {"current": "S4"},
    "last_updated": "2024-01-01T12:00:00Z"
  }
}
```

### 3. Get Consciousness State

```bash
curl http://localhost:8001/consciousness
```

---

## 📊 API Endpoints Overview

| Endpoint | Method | Purpose | Example Use Case |
|----------|--------|---------|------------------|
| `/metrics` | GET | Current IAS/GAS + traits | Health monitoring dashboard |
| `/consciousness` | GET | Full consciousness state | Identity visualization |
| `/events` | GET | Event log with filtering | Conversation analysis |
| `/reflections` | GET | Reflection history | Self-improvement insights |
| `/commitments` | GET | Goal tracking | Progress monitoring |
| `/stream` | WebSocket | Real-time events | Live dashboards |

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

### Query Recent Events

```bash
# Get last 10 events
curl "http://localhost:8001/events?limit=10"

# Get events by type
curl "http://localhost:8001/events?kind=reflection&limit=5"

# Get events by time range
curl "http://localhost:8001/events?since_ts=2024-01-01T00:00:00Z&until_ts=2024-01-01T23:59:59Z"
```

### Event Analysis Example

```python
import requests
from collections import Counter

def analyze_conversation_patterns():
    response = requests.get('http://localhost:8001/events?limit=1000')
    events = response.json()['events']

    # Count event types
    event_types = Counter(event['kind'] for event in events)
    print("Event Type Distribution:")
    for event_type, count in event_types.most_common():
        print(f"  {event_type}: {count}")

    # Analyze conversation flow
    user_messages = [e for e in events if e['kind'] == 'user_message']
    responses = [e for e in events if e['kind'] == 'response']

    print(f"\nConversation Stats:")
    print(f"  User messages: {len(user_messages)}")
    print(f"  AI responses: {len(responses)}")
    print(".2f"
    return events

events = analyze_conversation_patterns()
```

### Real-time Event Streaming

```python
import websocket
import json

def on_message(ws, message):
    event = json.loads(message)
    print(f"📝 New event: {event['kind']} - {event.get('content', '')[:50]}...")

def on_open(ws):
    print("🔗 Connected to PMM event stream")

def monitor_events():
    ws = websocket.WebSocketApp(
        "ws://localhost:8001/stream",
        on_message=on_message,
        on_open=on_open
    )
    ws.run_forever()

monitor_events()
```

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

# Get commitments by status
curl "http://localhost:8001/commitments?status=active"
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

**Ready to build with PMM?** Start with the consciousness endpoint - it's your window into PMM's evolving mind! 🚀🤖🔌
