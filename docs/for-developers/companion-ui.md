# 🖥️ Companion UI

The Companion UI is a Next.js dashboard for exploring PMM's identity, commitments, and reflections.

## Prerequisites
- Node.js 18+
- The Companion API running locally (`python scripts/run_companion_server.py`)

## Install dependencies

```bash
cd ui
npm install
```

## Start the development server

```bash
npm run dev
```

Visit [http://localhost:3000](http://localhost:3000) to load the dashboard. The UI expects the API at `http://localhost:8001` (the default from the companion server).

## Features

- **Identity view** – shows the current stage, trait vector, and evolution metrics.
- **Ledger timeline** – browse recent events with summaries.
- **Commitment tracker** – filter open vs. completed commitments.

If the API is offline you'll see a connection warning. Start it with:

```bash
python scripts/run_companion_server.py
```

## Customising the target database

Use the selector in the UI header to switch between the default ledger (`.data/pmm.db`) and any test DB shipped in `tests/data/`. The dropdown matches the query parameters accepted by the API (`?db=...`).

## Building for production

```bash
npm run build
npm run start
```

Deploy the `ui/.next` output behind any Node-friendly hosting solution (Vercel, Render, Docker, etc.).
