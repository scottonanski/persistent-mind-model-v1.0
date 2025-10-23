# Week 1 Action Plan: Ship v1.0 Foundation

**Goal**: Transform research prototype → shippable product  
**Timeline**: 7 days  
**Status**: Ready to execute

---

## Day 1: CLI Wrapper & Commands (Today)

### Morning: Core CLI Structure

**Create `pmm` command wrapper** (`pmm/cli/main.py`)

```python
#!/usr/bin/env python3
"""PMM: Own Your AI Before AGI"""

import click
from pathlib import Path

@click.group()
@click.version_option()
def cli():
    """Portable AI mind that works with any model."""
    pass

@cli.command()
@click.option('--port', default=3000, help='Port for web UI')
@click.option('--dev', is_flag=True, help='Development mode')
def start(port, dev):
    """Start PMM web interface."""
    click.echo(f"🚀 Starting PMM on http://localhost:{port}")
    # Launch FastAPI + Next.js
    
@cli.command()
def chat():
    """Start CLI chat mode."""
    click.echo("💬 PMM Chat (Ctrl+C to exit)")
    # Launch existing CLI chat

@cli.command()
@click.option('--jsonl', 'format_jsonl', is_flag=True, help='Export as JSONL')
@click.option('--json', 'format_json', is_flag=True, help='Export as JSON')
@click.argument('output', type=click.File('w'), default='-')
def export(format_jsonl, format_json, output):
    """Export mind database."""
    click.echo("📦 Exporting mind...")
    # Export logic

@cli.command()
@click.argument('input_file', type=click.File('r'))
def import_mind(input_file):
    """Import mind from JSONL/JSON."""
    click.echo("📥 Importing mind...")
    # Import logic

@cli.command()
@click.option('--sig', help='Signature file to verify against')
def verify(sig):
    """Verify database integrity."""
    click.echo("🔍 Verifying integrity...")
    # Verification logic

if __name__ == '__main__':
    cli()
```

**Tasks**:
- [ ] Create `pmm/cli/main.py` with Click framework
- [ ] Wire up existing commands (chat, companion)
- [ ] Add `export` command (JSONL format)
- [ ] Add `verify` command (hash chain check)
- [ ] Test all commands work

**Time**: 3 hours

### Afternoon: Model Management Commands

**Add model subcommands** (`pmm/cli/models.py`)

```python
@cli.group()
def model():
    """Manage AI models."""
    pass

@model.command()
def list():
    """List available models."""
    # Show configured providers + models
    
@model.command()
@click.argument('model_spec')  # e.g., "ollama:llama3.1"
def add(model_spec):
    """Add a new model."""
    # Parse spec, configure provider
    
@model.command()
@click.argument('model_spec')
def use(model_spec):
    """Switch to a different model."""
    # Update config, restart if needed
    
@model.command()
def info():
    """Show current model details."""
    # Display active model info
```

**Tasks**:
- [ ] Create model management commands
- [ ] Parse model specs (provider:model format)
- [ ] Store config in `~/.pmm/config.toml`
- [ ] Test model switching

**Time**: 2 hours

### Evening: Package & Install Script

**Create install script** (`install.sh`)

```bash
#!/bin/bash
set -e

echo "🚀 Installing PMM..."

# Detect OS
OS="$(uname -s)"
case "${OS}" in
    Linux*)     PLATFORM=linux;;
    Darwin*)    PLATFORM=macos;;
    *)          echo "Unsupported OS: ${OS}"; exit 1;;
esac

# Install Python dependencies
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 required. Install from python.org"
    exit 1
fi

# Clone or download
if [ -d "$HOME/.pmm" ]; then
    echo "📦 Updating existing installation..."
    cd "$HOME/.pmm"
    git pull
else
    echo "📦 Downloading PMM..."
    git clone https://github.com/scottonanski/pmm.git "$HOME/.pmm"
    cd "$HOME/.pmm"
fi

# Create venv
python3 -m venv .venv
source .venv/bin/activate

# Install
pip install -e .

# Create symlink
sudo ln -sf "$HOME/.pmm/.venv/bin/pmm" /usr/local/bin/pmm

echo "✅ PMM installed successfully!"
echo ""
echo "Get started:"
echo "  pmm start     # Launch web UI"
echo "  pmm chat      # CLI chat mode"
echo "  pmm --help    # Show all commands"
```

**Tasks**:
- [ ] Create `install.sh` script
- [ ] Test on macOS
- [ ] Test on Linux
- [ ] Add to README

**Time**: 2 hours

---

## Day 2: Docker & Compose

### Morning: Dockerfile

**Create production Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY pmm/ pmm/
COPY ui/ ui/

# Install Node.js for UI
RUN apt-get update && apt-get install -y nodejs npm
WORKDIR /app/ui
RUN npm install && npm run build

# Back to app root
WORKDIR /app

# Expose ports
EXPOSE 3000 8001

# Start command
CMD ["pmm", "start"]
```

**Tasks**:
- [ ] Create Dockerfile
- [ ] Build and test image
- [ ] Push to Docker Hub
- [ ] Document usage

**Time**: 2 hours

### Afternoon: Docker Compose

**Create `docker-compose.yml`**

```yaml
version: '3.8'

services:
  pmm:
    image: pmm/pmm:latest
    ports:
      - "3000:3000"
      - "8001:8001"
    volumes:
      - pmm-data:/data
    environment:
      - PMM_DB=/data/mind.db
      - PMM_PROVIDER=ollama
      - PMM_MODEL=llama3.1
    restart: unless-stopped

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama-data:/root/.ollama
    restart: unless-stopped

volumes:
  pmm-data:
  ollama-data:
```

**Tasks**:
- [ ] Create docker-compose.yml
- [ ] Test full stack
- [ ] Document setup
- [ ] Add to install script

**Time**: 2 hours

### Evening: Homebrew Formula

**Create Homebrew formula** (`pmm.rb`)

```ruby
class Pmm < Formula
  desc "Portable AI mind that works with any model"
  homepage "https://pmm.run"
  url "https://github.com/scottonanski/pmm/archive/v1.0.0.tar.gz"
  sha256 "..."
  license "MIT"

  depends_on "python@3.11"

  def install
    virtualenv_install_with_resources
  end

  test do
    system "#{bin}/pmm", "--version"
  end
end
```

**Tasks**:
- [ ] Create formula
- [ ] Test installation
- [ ] Submit to homebrew-core (later)
- [ ] Document for users

**Time**: 2 hours

---

## Day 3: Export & Verify Commands

### Morning: JSONL Export

**Implement export command** (`pmm/cli/export.py`)

```python
def export_jsonl(db_path: str, output: TextIO):
    """Export database to JSONL format."""
    log = EventLog(db_path)
    events = log.read_all()
    
    for event in events:
        # Convert to JSONL
        line = json.dumps({
            "id": event["id"],
            "ts": event["ts"],
            "kind": event["kind"],
            "content": event["content"],
            "meta": event.get("meta", {}),
            "hash": event.get("hash")
        })
        output.write(line + "\n")
```

**Tasks**:
- [ ] Implement JSONL export
- [ ] Add JSON export (pretty-printed)
- [ ] Test with large databases
- [ ] Add progress indicator

**Time**: 2 hours

### Afternoon: Import Command

**Implement import command** (`pmm/cli/import_cmd.py`)

```python
def import_jsonl(input_file: TextIO, db_path: str):
    """Import JSONL into new database."""
    log = EventLog(db_path)
    
    for line in input_file:
        event = json.loads(line)
        # Validate and append
        log.append(
            kind=event["kind"],
            content=event["content"],
            meta=event.get("meta", {})
        )
```

**Tasks**:
- [ ] Implement JSONL import
- [ ] Validate event structure
- [ ] Rebuild projections after import
- [ ] Test round-trip (export → import)

**Time**: 2 hours

### Evening: Verify Command

**Implement verification** (`pmm/cli/verify.py`)

```python
def verify_integrity(db_path: str) -> bool:
    """Verify hash chain integrity."""
    log = EventLog(db_path)
    
    try:
        log.verify_chain()
        click.echo("✅ Integrity verified")
        return True
    except Exception as e:
        click.echo(f"❌ Integrity check failed: {e}")
        return False
```

**Tasks**:
- [ ] Implement verify command
- [ ] Show detailed results
- [ ] Add signature verification (optional)
- [ ] Test with tampered databases

**Time**: 2 hours

---

## Day 4: UI Wireframes & Design

### Morning: Figma Wireframes

**Design screens**:
1. Home (Chat)
2. Your AI (Identity + Metrics)
3. Privacy (Export + Verify)
4. Models (Switch Providers)

**Tasks**:
- [ ] Create Figma project
- [ ] Design 4 main screens
- [ ] Mobile responsive layouts
- [ ] Component library

**Time**: 3 hours

### Afternoon: Design System

**Define components**:
- Colors (dark mode first)
- Typography
- Buttons, inputs, cards
- Icons (Lucide)
- Layout grid

**Tasks**:
- [ ] Create design tokens
- [ ] Document component specs
- [ ] Export assets
- [ ] Share with team (if any)

**Time**: 2 hours

### Evening: Technical Spec

**Write UI technical spec**:
- Framework: Next.js 15 + React 19
- Styling: Tailwind CSS 4
- Components: shadcn/ui
- State: React Query + Zustand
- API: FastAPI backend

**Tasks**:
- [ ] Document architecture
- [ ] List dependencies
- [ ] Plan API endpoints
- [ ] Estimate build time

**Time**: 2 hours

---

## Day 5: UI Foundation

### Morning: Next.js Setup

**Initialize UI project**

```bash
cd ui
npx create-next-app@latest . --typescript --tailwind --app
npm install @tanstack/react-query zustand lucide-react
npx shadcn-ui@latest init
```

**Tasks**:
- [ ] Set up Next.js project
- [ ] Configure Tailwind
- [ ] Install dependencies
- [ ] Create basic layout

**Time**: 2 hours

### Afternoon: API Client

**Create API client** (`ui/src/lib/api.ts`)

```typescript
const API_BASE = 'http://localhost:8001';

export const api = {
  async getSnapshot() {
    const res = await fetch(`${API_BASE}/snapshot`);
    return res.json();
  },
  
  async getMetrics() {
    const res = await fetch(`${API_BASE}/metrics?detailed=true`);
    return res.json();
  },
  
  async chat(message: string) {
    const res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message })
    });
    return res.json();
  }
};
```

**Tasks**:
- [ ] Create API client
- [ ] Add React Query hooks
- [ ] Test all endpoints
- [ ] Add error handling

**Time**: 2 hours

### Evening: Layout & Navigation

**Create app layout** (`ui/src/app/layout.tsx`)

```typescript
export default function RootLayout({ children }) {
  return (
    <html lang="en" className="dark">
      <body>
        <nav>
          <Link href="/">Chat</Link>
          <Link href="/ai">Your AI</Link>
          <Link href="/privacy">Privacy</Link>
          <Link href="/models">Models</Link>
        </nav>
        <main>{children}</main>
      </body>
    </html>
  );
}
```

**Tasks**:
- [ ] Create layout component
- [ ] Add navigation
- [ ] Set up routing
- [ ] Test navigation

**Time**: 2 hours

---

## Day 6: Core UI Components

### Morning: Chat Interface

**Build chat component** (`ui/src/components/chat.tsx`)

```typescript
export function Chat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  
  const sendMessage = async () => {
    const response = await api.chat(input);
    setMessages([...messages, { role: 'user', content: input }, response]);
    setInput('');
  };
  
  return (
    <div className="flex flex-col h-screen">
      <div className="flex-1 overflow-y-auto">
        {messages.map((msg, i) => (
          <Message key={i} {...msg} />
        ))}
      </div>
      <div className="p-4">
        <input value={input} onChange={e => setInput(e.target.value)} />
        <button onClick={sendMessage}>Send</button>
      </div>
    </div>
  );
}
```

**Tasks**:
- [ ] Build chat interface
- [ ] Add message components
- [ ] Implement streaming
- [ ] Test user flow

**Time**: 3 hours

### Afternoon: Your AI Tab

**Build identity view** (`ui/src/app/ai/page.tsx`)

```typescript
export default function AIPage() {
  const { data: metrics } = useQuery(['metrics'], api.getMetrics);
  
  return (
    <div className="space-y-6">
      <IdentityCard identity={metrics.identity} />
      <TraitsCard traits={metrics.traits} />
      <CommitmentHealth health={metrics.commitments} />
      <GrowthMetrics ias={metrics.ias} gas={metrics.gas} />
    </div>
  );
}
```

**Tasks**:
- [ ] Build identity cards
- [ ] Add trait visualizations
- [ ] Show commitment health
- [ ] Display growth metrics

**Time**: 3 hours

---

## Day 7: Polish & Testing

### Morning: Privacy & Models Tabs

**Build remaining tabs**

```typescript
// Privacy tab
export default function PrivacyPage() {
  return (
    <div>
      <DatabaseInfo />
      <ExportButton />
      <VerifyButton />
      <DeleteButton />
    </div>
  );
}

// Models tab
export default function ModelsPage() {
  return (
    <div>
      <CurrentModel />
      <AvailableModels />
      <AddModelButton />
    </div>
  );
}
```

**Tasks**:
- [ ] Build privacy tab
- [ ] Build models tab
- [ ] Wire up actions
- [ ] Test all flows

**Time**: 3 hours

### Afternoon: Integration Testing

**Test full stack**:
1. Install via script
2. Start with Docker Compose
3. Use UI to chat
4. Switch models
5. Export data
6. Verify integrity

**Tasks**:
- [ ] Write test checklist
- [ ] Test on clean machine
- [ ] Fix critical bugs
- [ ] Document issues

**Time**: 2 hours

### Evening: Documentation

**Write user docs**:
- Quick start guide
- Installation instructions
- Troubleshooting
- FAQ

**Tasks**:
- [ ] Write getting started guide
- [ ] Document common issues
- [ ] Create FAQ
- [ ] Update README

**Time**: 2 hours

---

## Success Criteria

By end of Week 1, we should have:

- [ ] Working `pmm` CLI with all core commands
- [ ] One-click install script (Mac/Linux)
- [ ] Docker Compose setup
- [ ] Export/import/verify commands working
- [ ] UI wireframes complete
- [ ] Basic UI foundation built
- [ ] Core components implemented
- [ ] Full stack tested

---

## Next Week Preview

**Week 2**: Polish, alpha testing, bug fixes  
**Week 3**: Beta launch prep, marketing content  
**Week 4**: Public launch, first 100 users

---

**Status**: Ready to start  
**First task**: Create `pmm/cli/main.py`  
**Let's ship this.**
