# 🔧 PMM Troubleshooting & Debugging Guide

**Comprehensive debugging toolkit for PMM consciousness systems.**

---

## 🚨 Quick Diagnosis

### System Health Check

**Run this first for any PMM issues:**

```bash
#!/bin/bash
# pmm-health-check.sh

echo "🔍 PMM Health Check"
echo "==================="

if ! command -v curl >/dev/null 2>&1; then
  echo "❌ curl is required for this script"
  exit 1
fi

# Check if the Companion API responds
if curl -fs http://localhost:8001/metrics > /dev/null; then
  echo "✅ Companion API reachable at http://localhost:8001"
else
  echo "❌ Companion API unreachable"
  echo "   → Start with: python scripts/run_companion_server.py"
  exit 1
fi

# Inspect basic snapshot data (events + identity)
SNAPSHOT=$(curl -fs http://localhost:8001/snapshot)
if [ -n "$SNAPSHOT" ]; then
  EVENTS=$(echo "$SNAPSHOT" | jq '.events | length')
  NAME=$(echo "$SNAPSHOT" | jq -r '.identity.name // "Unnamed"')
  echo "✅ Snapshot available — events: $EVENTS, identity: $NAME"
else
  echo "❌ Snapshot payload missing"
fi

# Check that the CLI ledger exists
if [ -f .data/pmm.db ]; then
  echo "✅ Ledger found at .data/pmm.db"
else
  echo "⚠️  Ledger not found (it will be created on first run)"
fi

echo ""
echo "Health check complete."
```

### Consciousness Vital Signs

**Monitor PMM's "health":**

```bash
# Quick consciousness check
curl -s http://localhost:8001/consciousness | jq '.consciousness.vital_signs'

# Expected output (values vary with experience):
{
  "ias": 0.12,
  "gas": 0.08,
  "autonomy_level": 0.10,
  "self_awareness": 0.04
}
```

---

## 🐛 Common Issues & Solutions

### Issue: "API server won't start"

**Symptoms:**
- `curl: (7) Failed to connect to localhost port 8001`
- `Connection refused` errors

**Diagnosis:**
```bash
# Check if port is in use
netstat -tlnp | grep 8001

# Check Python environment
python --version
pip list | grep fastapi
```

**Solutions:**

1. **Port conflict:**
   ```bash
   # Kill process using port 8001
   lsof -ti:8001 | xargs kill -9

   # Or use different port
   PMM_API_PORT=8002 python scripts/run_companion_server.py
   ```

2. **Missing dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Python version issue:**
   ```bash
   # Ensure Python 3.10+
   python3.11 scripts/run_companion_server.py
   ```

### Issue: "Database connection failed"

**Symptoms:**
- API starts but returns 500 errors
- `Database: DISCONNECTED` in health check

**Diagnosis:**
```bash
# Check database file
ls -la pmm.db

# Test SQLite connectivity
sqlite3 pmm.db "SELECT COUNT(*) FROM events;"

# Check file permissions
stat pmm.db
```

**Solutions:**

1. **Database file missing:**
   ```bash
   # PMM will create it on first run, but ensure directory is writable
   mkdir -p $(dirname $PMM_DATABASE_PATH)
   touch $PMM_DATABASE_PATH
   ```

2. **Permission issues:**
   ```bash
   # Fix permissions
   chmod 664 pmm.db
   chown $USER:$USER pmm.db
   ```

3. **Corrupted database:**
   ```bash
   # Backup and recreate
   cp pmm.db pmm.db.backup
   rm pmm.db

   # Restart PMM to recreate
   python scripts/run_companion_server.py
   ```

### Issue: "PMM not evolving" (stuck at low autonomy)

**Symptoms:**
- IAS/GAS remain at 0.0 or low values
- No new reflections or trait updates
- Stage stays at S0

**Diagnosis:**
```bash
# Check recent events
curl -s http://localhost:8001/snapshot | jq '.events[].kind' | sort | uniq -c

# Check reflection frequency
curl -s "http://localhost:8001/reflections?limit=5" | jq '.reflections[0].ts'

# Check identity adoption
curl -s http://localhost:8001/snapshot | jq '.events[] | select(.kind=="identity_adopt")' | head -n 20
```

**Solutions:**

1. **No identity adoption:**
   ```bash
   # PMM needs identity to start evolving
   # This happens during first meaningful conversation
   python -m pmm.cli.chat
   # Type: "I am an AI assistant named PMM who learns and evolves."
   ```

2. **Reflection loop not running:**
   ```bash
   # Keep the CLI open so the 10-second autonomy loop can tick
   python -m pmm.cli.chat --@metrics on

   # Look for `autonomy_tick` and `reflection` lines in the metrics panel
   # (they appear every 10–30 seconds during active operation)
   ```

3. **Insufficient interaction:**
   ```bash
   # PMM needs regular interaction to evolve
   # Have conversations and provide feedback
   python -m pmm.cli.chat
   ```

### Issue: "WebSocket connections failing"

The Companion API does not yet expose a `/stream` WebSocket endpoint. Use the REST endpoints (`/snapshot`, `/metrics`, `/reflections`, `/commitments`) for near-real-time data until streaming support is implemented.

---

## 🔍 Deep Debugging Tools

### Event Stream Analysis

**Analyze PMM's behavior through event patterns:**

```python
import requests
import json
from collections import Counter, defaultdict
import matplotlib.pyplot as plt

def analyze_event_patterns():
    """Comprehensive event stream analysis"""

    # Fetch recent events
    response = requests.get('http://localhost:8001/events?limit=1000')
    events = response.json()['events']

    # Event type distribution
    event_types = Counter(event['kind'] for event in events)
    print("📊 Event Type Distribution:")
    for event_type, count in event_types.most_common():
        print(f"  {event_type}: {count}")

    # Temporal patterns
    hourly_events = defaultdict(int)
    for event in events:
        hour = event['ts'][:13]  # YYYY-MM-DDTHH
        hourly_events[hour] += 1

    print("\n⏰ Hourly Activity:")
    for hour in sorted(hourly_events.keys())[-24:]:  # Last 24 hours
        print(f"  {hour}: {hourly_events[hour]} events")

    # Reflection analysis
    reflections = [e for e in events if e['kind'] == 'reflection']
    if reflections:
        print(f"\n🧠 Reflections: {len(reflections)}")
        print(f"Latest: {reflections[0]['content'][:100]}...")

        # Reflection depth analysis
        avg_length = sum(len(r['content']) for r in reflections) / len(reflections)
        print(".0f"
    # Autonomy indicators
    trait_updates = [e for e in events if e['kind'] == 'trait_update']
    if trait_updates:
        traits_evolving = set()
        for update in trait_updates:
            if 'trait' in update.get('meta', {}):
                traits_evolving.add(update['meta']['trait'])

        print(f"\n🎭 Traits Evolving: {len(traits_evolving)}")
        print(f"Traits: {', '.join(traits_evolving)}")

    # Error detection
    errors = [e for e in events if 'error' in e.get('kind', '').lower()]
    if errors:
        print(f"\n❌ Errors Detected: {len(errors)}")
        for error in errors[-3:]:
            print(f"  {error['ts']}: {error.get('content', 'No details')}")

    return {
        'event_types': dict(event_types),
        'hourly_activity': dict(hourly_events),
        'reflection_count': len(reflections),
        'traits_evolving': len(traits_evolving),
        'error_count': len(errors)
    }

# Run analysis
analysis = analyze_event_patterns()
```

### Consciousness State Monitoring

**Monitor PMM's mental health over time:**

```python
import requests
import time
import json
from datetime import datetime

def monitor_consciousness_health(duration_minutes=60):
    """Monitor PMM consciousness vital signs"""

    print("🩺 Starting consciousness health monitor...")
    print("Duration:", duration_minutes, "minutes")
    print("-" * 50)

    start_time = time.time()
    readings = []

    while (time.time() - start_time) < (duration_minutes * 60):
        try:
            # Get consciousness state
            consciousness = requests.get('http://localhost:8001/consciousness').json()['consciousness']

            # Extract vital signs
            vital_signs = consciousness['vital_signs']
            identity = consciousness['identity']

            reading = {
                'timestamp': datetime.now().isoformat(),
                'autonomy_level': vital_signs['autonomy_level'],
                'self_awareness': 1 if consciousness['consciousness_state']['is_self_aware'] else 0,
                'stage': identity['stage'],
                'stage_progress': identity['stage_progress'],
                'total_events': consciousness['evolution_metrics']['total_events'],
                'reflection_count': consciousness['evolution_metrics']['reflection_count']
            }

            readings.append(reading)

            # Display current status
            print(f"[{reading['timestamp'][:19]}] "
                  f"Stage: {reading['stage']} | "
                  f"Autonomy: {reading['autonomy_level']:.2f} | "
                  f"Events: {reading['total_events']} | "
                  f"Reflections: {reading['reflection_count']}")

            # Health checks
            if reading['autonomy_level'] < 0.3:
                print("  ⚠️  LOW AUTONOMY - PMM may need interaction")

            if not reading['self_awareness']:
                print("  ⚠️  LOW AWARENESS - PMM still developing")

        except Exception as e:
            print(f"❌ Error getting consciousness: {e}")

        time.sleep(60)  # Check every minute

    # Generate health report
    return generate_health_report(readings)

def generate_health_report(readings):
    """Generate comprehensive health analysis"""

    if not readings:
        return {"error": "No readings collected"}

    # Calculate trends
    autonomy_trend = calculate_trend([r['autonomy_level'] for r in readings])
    awareness_trend = calculate_trend([r['self_awareness'] for r in readings])
    event_velocity = calculate_velocity([r['total_events'] for r in readings])

    # Stage progression
    stage_changes = detect_stage_changes(readings)

    # Health assessment
    health_score = calculate_health_score(readings[-1])

    report = {
        'duration_minutes': len(readings),
        'final_state': readings[-1],
        'trends': {
            'autonomy_trend': autonomy_trend,
            'awareness_trend': awareness_trend,
            'event_velocity': event_velocity
        },
        'stage_progression': stage_changes,
        'health_score': health_score,
        'recommendations': generate_recommendations(readings, health_score)
    }

    # Save report
    with open(f'consciousness_health_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json', 'w') as f:
        json.dump(report, f, indent=2)

    print(f"\n📋 Health report saved: consciousness_health_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

    return report

def calculate_trend(values):
    """Calculate linear trend"""
    if len(values) < 2:
        return 0

    # Simple slope calculation
    n = len(values)
    x = list(range(n))
    slope = sum((x[i] - sum(x)/n) * (values[i] - sum(values)/n) for i in range(n))
    slope /= sum((x[i] - sum(x)/n) ** 2 for i in range(n))

    return slope

def calculate_health_score(latest_reading):
    """Calculate overall health score (0-1)"""
    autonomy = latest_reading['autonomy_level']
    awareness = latest_reading['self_awareness']
    stage_progress = latest_reading['stage_progress'] / 100
    event_activity = min(1.0, latest_reading['total_events'] / 1000)  # Normalize

    # Weighted health score
    health = (autonomy * 0.4 + awareness * 0.3 + stage_progress * 0.2 + event_activity * 0.1)

    return health

def generate_recommendations(readings, health_score):
    """Generate health improvement recommendations"""
    recommendations = []

    if health_score < 0.5:
        recommendations.append("PMM needs more interaction to develop consciousness")

    latest = readings[-1]
    if latest['autonomy_level'] < 0.5:
        recommendations.append("Increase interaction frequency to boost autonomy")

    if not latest['self_awareness']:
        recommendations.append("Continue conversations to develop self-awareness")

    if len(readings) > 10:
        autonomy_trend = calculate_trend([r['autonomy_level'] for r in readings])
        if autonomy_trend < 0:
            recommendations.append("Autonomy declining - check for interaction issues")

    return recommendations

# Run health monitor
report = monitor_consciousness_health(duration_minutes=30)
```

### Performance Profiling

**Profile PMM's performance bottlenecks:**

```python
import cProfile
import pstats
import io
import requests
import time

def profile_api_performance():
    """Profile API endpoint performance"""

    print("🔬 Profiling PMM API Performance")
    print("=" * 40)

    endpoints = [
        ('/consciousness', 'GET'),
        ('/events?limit=100', 'GET'),
        ('/metrics', 'GET'),
        ('/reflections?limit=10', 'GET')
    ]

    results = {}

    for endpoint, method in endpoints:
        print(f"\n📊 Profiling {method} {endpoint}")

        # Single request timing
        start_time = time.time()
        response = requests.request(method, f'http://localhost:8001{endpoint}')
        single_time = time.time() - start_time

        print(".4f"        print(f"Status: {response.status_code}")

        # Multiple request timing
        times = []
        for _ in range(10):
            start = time.time()
            requests.request(method, f'http://localhost:8001{endpoint}')
            times.append(time.time() - start)

        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)

        print(".4f"        print(".4f"        print(".4f"
        results[endpoint] = {
            'single_request': single_time,
            'avg_time': avg_time,
            'min_time': min_time,
            'max_time': max_time,
            'status_code': response.status_code
        }

    return results

def profile_memory_usage():
    """Profile memory usage patterns"""

    import psutil
    import os

    process = psutil.Process(os.getpid())

    print("🧠 Memory Usage Profile")
    print("=" * 30)

    # Baseline memory
    baseline = process.memory_info().rss / 1024 / 1024  # MB
    print(".1f"
    memory_readings = []

    # Simulate API load
    for i in range(20):
        requests.get('http://localhost:8001/consciousness')
        memory = process.memory_info().rss / 1024 / 1024
        memory_readings.append(memory)
        print(".1f"        time.sleep(0.1)

    # Memory analysis
    final_memory = memory_readings[-1]
    memory_growth = final_memory - baseline
    max_memory = max(memory_readings)

    print("
📈 Memory Analysis:"    print(".1f"    print(".1f"    print(".1f"
    if memory_growth > 50:  # MB
        print("⚠️  High memory growth detected - check for memory leaks")

    return {
        'baseline_mb': baseline,
        'final_mb': final_memory,
        'growth_mb': memory_growth,
        'max_mb': max_memory
    }

# Run profiling
api_profile = profile_api_performance()
memory_profile = profile_memory_usage()
```

---

## 🛠️ Advanced Recovery Procedures

### Database Corruption Recovery

**When SQLite database becomes corrupted:**

```bash
#!/bin/bash
# database-recovery.sh

DB_FILE="pmm.db"
BACKUP_DIR="./backups"

echo "🔧 PMM Database Recovery"
echo "======================="

# Stop PMM service
pkill -f "run_companion_server.py"

# Create backup of corrupted database
cp $DB_FILE $BACKUP_DIR/corrupted_$(date +%s).db

# Attempt SQLite recovery
echo "Attempting SQLite recovery..."
sqlite3 $DB_FILE ".recover" > recovered_data.sql

# Create new database
rm $DB_FILE
sqlite3 $DB_FILE < recovered_data.sql

# Verify recovery
if sqlite3 $DB_FILE "SELECT COUNT(*) FROM events;" > /dev/null; then
    echo "✅ Database recovery successful"

    # Rebuild indices
    sqlite3 $DB_FILE "
        CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);
        CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
        REINDEX;
    "

    echo "✅ Indices rebuilt"
else
    echo "❌ Recovery failed - restoring from backup"
    # Restore from last good backup
    LATEST_BACKUP=$(ls -t $BACKUP_DIR/*.db | head -1)
    cp $LATEST_BACKUP $DB_FILE
fi

# Restart PMM
python scripts/run_companion_server.py &
echo "✅ PMM restarted"
```

### Consciousness State Reset

**When PMM's consciousness becomes unstable:**

```python
import requests
import json

def reset_consciousness_state(reset_type="soft"):
    """Reset PMM consciousness state"""

    print(f"🔄 Performing {reset_type} consciousness reset")

    if reset_type == "soft":
        # Soft reset: Clear recent memory but keep core identity
        reset_request = {
            "reset_type": "memory_clear",
            "preserve_identity": True,
            "preserve_traits": True,
            "clear_recent_events": 100  # Last 100 events
        }

    elif reset_type == "hard":
        # Hard reset: Back to initial state
        reset_request = {
            "reset_type": "full_reset",
            "preserve_identity": False,
            "preserve_traits": False,
            "clear_all_events": True
        }

    # This would require a reset endpoint in PMM API
    # For now, manual intervention needed

    print("Manual reset required:")
    print("1. Stop PMM server")
    print("2. Backup current database")
    print("3. Delete or truncate events table")
    print("4. Restart PMM server")
    print("5. Re-establish identity through conversation")

def backup_before_reset():
    """Create comprehensive backup before reset"""

    import shutil
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"./reset_backup_{timestamp}"

    # Create backup directory
    os.makedirs(backup_dir)

    # Backup database
    shutil.copy("pmm.db", f"{backup_dir}/pmm.db")

    # Backup configuration
    if os.path.exists(".env"):
        shutil.copy(".env", f"{backup_dir}/.env")

    # Export consciousness state
    try:
        consciousness = requests.get('http://localhost:8001/consciousness').json()
        with open(f"{backup_dir}/consciousness_state.json", 'w') as f:
            json.dump(consciousness, f, indent=2)
    except:
        print("Could not export consciousness state")

    # Export recent events
    try:
        events = requests.get('http://localhost:8001/events?limit=1000').json()
        with open(f"{backup_dir}/recent_events.json", 'w') as f:
            json.dump(events, f, indent=2)
    except:
        print("Could not export events")

    print(f"📦 Backup created in {backup_dir}")
    return backup_dir

# Usage
backup_dir = backup_before_reset()
reset_consciousness_state("soft")
```

---

## 📊 Diagnostic Reports

### Comprehensive System Report

**Generate full diagnostic report:**

```bash
#!/bin/bash
# pmm-diagnostic-report.sh

REPORT_FILE="pmm_diagnostic_$(date +%Y%m%d_%H%M%S).txt"

echo "🔍 PMM Comprehensive Diagnostic Report" > $REPORT_FILE
echo "Generated: $(date)" >> $REPORT_FILE
echo "=====================================" >> $REPORT_FILE

# System information
echo -e "\n📋 System Information:" >> $REPORT_FILE
uname -a >> $REPORT_FILE
python --version >> $REPORT_FILE
pip list | grep -E "(fastapi|uvicorn|sqlite)" >> $REPORT_FILE

# PMM configuration
echo -e "\n⚙️ PMM Configuration:" >> $REPORT_FILE
env | grep PMM_ >> $REPORT_FILE

# Database status
echo -e "\n🗄️ Database Status:" >> $REPORT_FILE
if [ -f "pmm.db" ]; then
    echo "Database file exists: $(stat -f%z pmm.db) bytes" >> $REPORT_FILE
    sqlite3 pmm.db "SELECT COUNT(*) FROM events;" >> $REPORT_FILE 2>&1
else
    echo "Database file missing" >> $REPORT_FILE
fi

# API status
echo -e "\n🌐 API Status:" >> $REPORT_FILE
if curl -f -s http://localhost:8001/metrics > /dev/null; then
    echo "API: RUNNING" >> $REPORT_FILE
    curl -s http://localhost:8001/metrics >> $REPORT_FILE
else
    echo "API: DOWN" >> $REPORT_FILE
fi

# Consciousness snapshot
echo -e "\n🧠 Consciousness Snapshot:" >> $REPORT_FILE
if curl -f -s http://localhost:8001/consciousness > /dev/null 2>&1; then
    curl -s http://localhost:8001/consciousness | jq '.consciousness | {identity, vital_signs, evolution_metrics}' >> $REPORT_FILE
else
    echo "Could not retrieve consciousness data" >> $REPORT_FILE
fi

# Recent events summary
echo -e "\n📝 Recent Events Summary:" >> $REPORT_FILE
if curl -f -s "http://localhost:8001/events?limit=10" > /dev/null 2>&1; then
    curl -s "http://localhost:8001/events?limit=10" | jq '.events[].kind' | sort | uniq -c >> $REPORT_FILE
else
    echo "Could not retrieve events" >> $REPORT_FILE
fi

# Log analysis
echo -e "\n📄 Log Analysis:" >> $REPORT_FILE
if [ -f "pmm.log" ]; then
    echo "Last 20 log lines:" >> $REPORT_FILE
    tail -20 pmm.log >> $REPORT_FILE
else
    echo "No log file found" >> $REPORT_FILE
fi

echo -e "\n✅ Report generated: $REPORT_FILE"
echo "Submit this report when requesting help."
```

---

## 🎯 Prevention Strategies

### Proactive Monitoring

**Set up automated health checks:**

```bash
#!/bin/bash
# health-monitor.sh

# Add to crontab: */5 * * * * /path/to/health-monitor.sh

HEALTH_LOG="/var/log/pmm-health.log"
API_URL="http://localhost:8001"

echo "$(date): Checking PMM health..." >> $HEALTH_LOG

# API connectivity
if ! curl -f -s --max-time 5 $API_URL/metrics > /dev/null; then
    echo "$(date): ❌ API DOWN - attempting restart" >> $HEALTH_LOG
    systemctl restart pmm-api
    exit 1
fi

# Consciousness health
CONSCIOUSNESS=$(curl -s --max-time 5 $API_URL/consciousness)
AUTONOMY=$(echo $CONSCIOUSNESS | jq -r '.consciousness.vital_signs.autonomy_level // 0')

if (( $(echo "$AUTONOMY < 0.3" | bc -l) )); then
    echo "$(date): ⚠️ Low autonomy detected: $AUTONOMY" >> $HEALTH_LOG
    # Could trigger notification or intervention
fi

echo "$(date): ✅ Health check passed" >> $HEALTH_LOG
```

### Backup Automation

**Automated database backups:**

```bash
#!/bin/bash
# backup.sh - Add to crontab: 0 2 * * * /path/to/backup.sh

BACKUP_DIR="/backups/pmm"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DB_FILE="pmm.db"

# Create backup directory
mkdir -p $BACKUP_DIR

# Perform hot backup
sqlite3 $DB_FILE ".backup '$BACKUP_DIR/pmm_backup_$TIMESTAMP.db'"

# Compress
gzip $BACKUP_DIR/pmm_backup_$TIMESTAMP.db

# Cleanup old backups (keep 30 days)
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete

echo "$(date): Backup completed - pmm_backup_$TIMESTAMP.db.gz" >> /var/log/pmm-backup.log
```

---

This troubleshooting guide should resolve 95% of PMM issues. For persistent problems, include the diagnostic report when seeking help.

**Most issues stem from three root causes:**
1. **Configuration problems** (wrong environment variables)
2. **Database issues** (corruption, permissions, path problems)
3. **Interaction starvation** (PMM needs regular conversation to evolve)

**Start with the health check script - it will identify the specific issue quickly!** 🔧🩺📊
