# ⚙️ PMM Configuration & Deployment Guide

**Complete technical reference for configuring, deploying, and operating PMM in production.**

---

## 🏗️ Configuration Architecture

PMM uses a layered configuration system:

```
Environment Variables (highest priority)
├── Config Files (pmm/config/)
├── Runtime Defaults (fallback)
└── Hardcoded Constants (lowest priority)
```

---

## 🔧 Core Configuration Options

### Runtime Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PMM_DATABASE_PATH` | `pmm.db` | SQLite database file location |
| `PMM_LOG_LEVEL` | `INFO` | Logging verbosity (DEBUG, INFO, WARNING, ERROR) |
| `PMM_LOG_FILE` | `pmm.log` | Log file path (or `stdout` for console) |
| `PMM_STAGE` | `auto` | Initial stage (S0, S1, S2, S3, S4, or `auto`) |
| `PMM_IDENTITY_NAME` | `PMM` | AI's self-chosen name |

### Autonomy Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PMM_AUTONOMY_ENABLED` | `true` | Enable/disable background autonomy loop |
| `PMM_REFLECTION_INTERVAL` | `60` | Seconds between reflection cycles |
| `PMM_TRAIT_UPDATE_ENABLED` | `true` | Allow personality trait evolution |
| `PMM_COMMITMENT_TRACKING` | `true` | Enable goal-oriented behavior |

### API Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PMM_API_HOST` | `localhost` | API server bind address |
| `PMM_API_PORT` | `8001` | API server port |
| `PMM_API_WORKERS` | `1` | Number of API worker processes |
| `PMM_CORS_ORIGINS` | `*` | Allowed CORS origins (comma-separated) |
| `PMM_API_KEY` | `none` | API authentication key |

### Performance Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `PMM_MAX_EVENTS_CACHE` | `1000` | Events to keep in memory cache |
| `PMM_REFLECTION_DEPTH` | `standard` | Reflection analysis depth (basic/standard/deep) |
| `PMM_TRAIT_UPDATE_BATCH` | `10` | Trait updates per batch |
| `PMM_COMMITMENT_MAX_ACTIVE` | `50` | Maximum concurrent commitments |

---

## 🚀 Deployment Scenarios

### Development Setup

**Single-machine development with hot reload:**

```bash
# Environment setup
export PMM_DATABASE_PATH=./dev.db
export PMM_LOG_LEVEL=DEBUG
export PMM_API_HOST=localhost
export PMM_API_PORT=8001

# Start development server
python scripts/run_companion_server.py
```

### Production Deployment

**Docker container with persistent storage:**

```dockerfile
FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY pmm/ ./pmm/
COPY scripts/ ./scripts/

# Create data directory
RUN mkdir -p /data
VOLUME /data

# Environment variables
ENV PMM_DATABASE_PATH=/data/pmm.db
ENV PMM_LOG_LEVEL=INFO
ENV PMM_API_HOST=0.0.0.0
ENV PMM_API_PORT=8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

EXPOSE 8001
CMD ["python", "scripts/run_companion_server.py"]
```

**Docker Compose production stack:**

```yaml
version: '3.8'
services:
  pmm-api:
    build: .
    ports:
      - "8001:8001"
    environment:
      - PMM_DATABASE_PATH=/data/pmm.db
      - PMM_LOG_LEVEL=INFO
      - PMM_API_HOST=0.0.0.0
      - PMM_CORS_ORIGINS=https://yourdomain.com
    volumes:
      - ./data:/data
      - ./logs:/app/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  pmm-ui:
    image: nginx:alpine
    ports:
      - "3000:80"
    volumes:
      - ./ui/dist:/usr/share/nginx/html
    depends_on:
      - pmm-api
```

### Cloud Deployment

**AWS EC2 with RDS:**

```bash
# EC2 user data script
#!/bin/bash
yum update -y
yum install -y python39 git

cd /home/ec2-user
git clone https://github.com/yourorg/pmm.git
cd pmm

pip3 install -r requirements.txt

# Configure for production
cat > .env << EOF
PMM_DATABASE_URL=postgresql://user:pass@rds-host:5432/pmm
PMM_API_HOST=0.0.0.0
PMM_API_PORT=8001
PMM_LOG_LEVEL=INFO
PMM_API_KEY=your-production-key
EOF

# Start with systemd
sudo cp scripts/pmm-api.service /etc/systemd/system/
sudo systemctl enable pmm-api
sudo systemctl start pmm-api
```

### Kubernetes Deployment

**Helm chart configuration:**

```yaml
# values.yaml
pmm:
  image:
    repository: yourorg/pmm
    tag: "1.0.0"

  config:
    databasePath: "/data/pmm.db"
    logLevel: "INFO"
    apiHost: "0.0.0.0"
    apiPort: "8001"

  persistence:
    enabled: true
    size: 10Gi

  service:
    type: ClusterIP
    port: 8001

ingress:
  enabled: true
  hosts:
    - pmm.yourdomain.com
```

---

## 📊 Monitoring & Observability

### Health Checks

**Application health endpoint:**

```bash
# Basic health
curl http://localhost:8001/health

# Response
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime": 86400,
  "database": "connected",
  "last_event": "2024-01-01T12:00:00Z"
}
```

### Logging Configuration

**Structured JSON logging:**

```python
import logging
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }

        # Add extra fields
        if hasattr(record, 'pmm_event_id'):
            log_entry['event_id'] = record.pmm_event_id
        if hasattr(record, 'pmm_stage'):
            log_entry['stage'] = record.pmm_stage

        return json.dumps(log_entry)
```

**Log levels by component:**

```python
LOGGING_CONFIG = {
    'version': 1,
    'formatters': {
        'json': {
            '()': JSONFormatter,
        }
    },
    'handlers': {
        'file': {
            'class': 'logging.FileHandler',
            'filename': 'pmm.log',
            'formatter': 'json',
            'level': 'INFO'
        }
    },
    'loggers': {
        'pmm.runtime': {'level': 'DEBUG'},
        'pmm.api': {'level': 'INFO'},
        'pmm.storage': {'level': 'WARNING'}
    }
}
```

### Metrics Collection

**Prometheus metrics export:**

```python
from prometheus_client import Counter, Gauge, Histogram, generate_latest

# Core metrics
EVENTS_PROCESSED = Counter('pmm_events_total', 'Total events processed')
ACTIVE_COMMITMENTS = Gauge('pmm_commitments_active', 'Active commitments')
REFLECTION_DURATION = Histogram('pmm_reflection_duration_seconds', 'Reflection processing time')

# Consciousness metrics
CONSCIOUSNESS_LEVEL = Gauge('pmm_consciousness_level', 'Current consciousness level')
AUTONOMY_SCORE = Gauge('pmm_autonomy_score', 'Current autonomy score')

def update_metrics():
    """Update Prometheus metrics"""
    from pmm.runtime.metrics import get_current_metrics

    metrics = get_current_metrics()
    CONSCIOUSNESS_LEVEL.set(metrics['consciousness_level'])
    AUTONOMY_SCORE.set(metrics['autonomy_score'])
    ACTIVE_COMMITMENTS.set(len(metrics['active_commitments']))

# Metrics endpoint
@app.route('/metrics')
def metrics():
    update_metrics()
    return generate_latest()
```

### Alerting Rules

**Prometheus alerting configuration:**

```yaml
groups:
  - name: pmm
    rules:
      - alert: PMMDown
        expr: up{job="pmm-api"} == 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "PMM API is down"

      - alert: PMMLowAutonomy
        expr: pmm_autonomy_score < 0.5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "PMM autonomy score is low"

      - alert: PMMHighErrorRate
        expr: rate(pmm_api_errors_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High PMM API error rate"
```

---

## 🔄 Backup & Recovery

### Database Backup Strategy

**Automated SQLite backups:**

```bash
#!/bin/bash
# backup.sh

DB_PATH="/data/pmm.db"
BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create backup with WAL checkpoint
sqlite3 $DB_PATH "PRAGMA wal_checkpoint(PASSIVE);"
cp $DB_PATH $BACKUP_DIR/pmm_backup_$TIMESTAMP.db

# Compress and retain last 30 days
gzip $BACKUP_DIR/pmm_backup_$TIMESTAMP.db
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete

echo "Backup completed: pmm_backup_$TIMESTAMP.db.gz"
```

**Point-in-time recovery:**

```bash
#!/bin/bash
# restore.sh

BACKUP_FILE="$1"
DB_PATH="/data/pmm.db"

# Stop PMM service
systemctl stop pmm-api

# Restore from backup
gunzip -c $BACKUP_FILE > $DB_PATH

# Verify integrity
sqlite3 $DB_PATH "PRAGMA integrity_check;"

# Restart service
systemctl start pmm-api

echo "Restore completed from $BACKUP_FILE"
```

### Configuration Backup

**Configuration versioning:**

```bash
# Backup current config
cp .env .env.backup.$(date +%s)

# Version control important configs
git add config/
git commit -m "Backup configuration changes"
```

---

## 🔒 Security Configuration

### API Authentication

**API key middleware:**

```python
from flask import request, jsonify
import os

API_KEY = os.getenv('PMM_API_KEY')

def require_api_key(f):
    def decorated_function(*args, **kwargs):
        if API_KEY and request.headers.get('Authorization') != f'Bearer {API_KEY}':
            return jsonify({'error': 'Invalid API key'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/consciousness')
@require_api_key
def get_consciousness():
    # Protected endpoint
    pass
```

### Database Encryption

**SQLite encryption at rest:**

```python
import sqlite3
from cryptography.fernet import Fernet

# Generate encryption key (store securely!)
key = Fernet.generate_key()
cipher = Fernet(key)

def encrypt_database(db_path, key):
    """Encrypt SQLite database file"""
    with open(db_path, 'rb') as f:
        data = f.read()

    encrypted = cipher.encrypt(data)

    with open(db_path + '.encrypted', 'wb') as f:
        f.write(encrypted)

def decrypt_database(encrypted_path, key):
    """Decrypt SQLite database file"""
    with open(encrypted_path, 'rb') as f:
        encrypted = f.read()

    decrypted = cipher.decrypt(encrypted)

    with open(encrypted_path.replace('.encrypted', ''), 'wb') as f:
        f.write(decrypted)
```

### Network Security

**Production firewall rules:**

```bash
# UFW rules for PMM API
ufw allow 22/tcp                    # SSH
ufw allow 8001/tcp                  # PMM API
ufw --force enable                  # Enable firewall

# Nginx reverse proxy with SSL
server {
    listen 443 ssl http2;
    server_name pmm.yourdomain.com;

    ssl_certificate /etc/ssl/pmm.crt;
    ssl_certificate_key /etc/ssl/pmm.key;

    location / {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 🧪 Testing & Validation

### Configuration Testing

**Validate configuration before deployment:**

```python
def validate_config():
    """Validate PMM configuration"""
    required_vars = [
        'PMM_DATABASE_PATH',
        'PMM_API_HOST',
        'PMM_API_PORT'
    ]

    missing = []
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)

    if missing:
        raise ValueError(f"Missing required environment variables: {missing}")

    # Validate database path
    db_path = os.getenv('PMM_DATABASE_PATH')
    if not os.access(os.path.dirname(db_path), os.W_OK):
        raise ValueError(f"Cannot write to database directory: {db_path}")

    # Validate API port
    port = int(os.getenv('PMM_API_PORT', 8001))
    if not (1024 <= port <= 65535):
        raise ValueError(f"Invalid API port: {port}")

    print("✅ Configuration validation passed")
```

### Integration Testing

**End-to-end deployment testing:**

```bash
#!/bin/bash
# test-deployment.sh

echo "Testing PMM deployment..."

# Test API health
if ! curl -f http://localhost:8001/health > /dev/null 2>&1; then
    echo "❌ API health check failed"
    exit 1
fi

# Test database connectivity
if ! curl -f "http://localhost:8001/events?limit=1" > /dev/null 2>&1; then
    echo "❌ Database connectivity test failed"
    exit 1
fi

# Test consciousness endpoint
if ! curl -f http://localhost:8001/consciousness > /dev/null 2>&1; then
    echo "❌ Consciousness endpoint test failed"
    exit 1
fi

echo "✅ All deployment tests passed"
```

---

## 📈 Performance Tuning

### Memory Optimization

**Large database performance:**

```python
# Optimize SQLite for read-heavy workloads
PRAGMA journal_mode = WAL;        -- Write-ahead logging
PRAGMA synchronous = NORMAL;      -- Balanced safety/performance
PRAGMA cache_size = -64000;       -- 64MB cache
PRAGMA temp_store = MEMORY;       -- Temp tables in memory
PRAGMA mmap_size = 268435456;     -- 256MB memory mapping
```

### Query Optimization

**Efficient event queries:**

```python
# Create optimized indices
CREATE INDEX idx_events_kind_ts ON events(kind, ts);
CREATE INDEX idx_events_ts ON events(ts DESC);
CREATE INDEX idx_events_hash ON events(hash);

# Use covering indices for common queries
SELECT id, ts, kind FROM events
WHERE ts > ? AND kind = ?
ORDER BY ts DESC LIMIT 100;
```

### Caching Strategy

**Multi-level caching:**

```python
from cachetools import TTLCache, LRUCache

# Short-term memory cache (5 minutes)
memory_cache = TTLCache(maxsize=1000, ttl=300)

# Long-term file cache (1 hour)
file_cache = LRUCache(maxsize=5000)

def get_cached_events(query_key):
    """Get events with caching"""
    if query_key in memory_cache:
        return memory_cache[query_key]

    if query_key in file_cache:
        result = file_cache[query_key]
        memory_cache[query_key] = result
        return result

    # Compute result
    result = compute_expensive_query(query_key)

    # Cache results
    memory_cache[query_key] = result
    file_cache[query_key] = result

    return result
```

---

## 🚨 Troubleshooting Guide

### Common Issues

**API returns 500 errors:**
```bash
# Check logs
tail -f pmm.log

# Test database connectivity
sqlite3 pmm.db "SELECT COUNT(*) FROM events;"

# Restart service
systemctl restart pmm-api
```

**High memory usage:**
```bash
# Check memory usage
ps aux | grep pmm

# Reduce cache sizes
export PMM_MAX_EVENTS_CACHE=500
export PMM_REFLECTION_DEPTH=basic
```

**Slow response times:**
```bash
# Profile API endpoints
python -m cProfile scripts/run_companion_server.py

# Optimize database queries
EXPLAIN QUERY PLAN SELECT * FROM events WHERE kind = 'reflection';
```

**WebSocket connection issues:**
```bash
# Check WebSocket port
netstat -tlnp | grep 8001

# Test WebSocket connection
websocat ws://localhost:8001/stream
```

---

## 📞 Support & Resources

- **Configuration Issues**: Check this guide's troubleshooting section
- **Performance Problems**: Review monitoring and tuning sections
- **Security Questions**: See security configuration examples
- **GitHub Issues**: [Report deployment issues](../../issues)
- **Community**: [Deployment discussions](../../discussions)

**Ready to deploy PMM to production?** Start with the Docker Compose example - it provides a complete, production-ready stack! 🚀⚙️🛠️
