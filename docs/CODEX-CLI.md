# Codex CLI integration

Codex accesses PMM through its local STDIO MCP server. Codex can read PMM's
persistent history and explicitly ask PMM to run a managed turn. PMM's configured
model generates that turn; Codex is not the model inside PMM. This integration
does not automatically capture Codex conversations or inject PMM history into
every Codex prompt.

## Setup

From the PMM checkout, using its virtual environment:

```bash
.venv/bin/python -m pip install -e . --no-deps
.venv/bin/pmm-codex check
.venv/bin/pmm-codex run
```

If no PMM registration exists, configure one first:

```bash
.venv/bin/pmm-codex configure --db "<ABSOLUTE_DB_PATH>" --model "<MODEL_NAME>"
```

`configure` registers the current Python interpreter and checkout with
`codex mcp add`. It replaces the registration with the same name; use
`pmm-codex --name another-name configure ...` for a separate connection.
Keep the checkout and interpreter available. Configuration does not initialize
a missing ledger: `check` reports the missing database, while the first
`pmm_turn` can initialize it through the normal writer path. The selected PMM
provider must be available for turns (Ollama service/model, or OpenAI API key).
Read-only tools do not need a model service or API key.

`check` reads Codex's registration, launches that exact command, initializes
MCP, checks the exposed and enabled tools, and calls `pmm_status`. It never
generates a reply or creates a ledger. A successful check proves that transport
and ledger reads work; it does not prove model credentials or generation work.

`run` launches Codex with a per-invocation 300-second MCP tool timeout, allowing
PMM's 240-second turn subprocess to report its result. Other Codex settings
remain inherited. Forward additional CLI arguments after `--`:

```bash
.venv/bin/pmm-codex run -- exec "Use pmm_status to check the PMM connection."
```

Without the installed entry point, use
`.venv/bin/python -m pmm.runtime.codex_cli check` (or `run`/`configure`).
Restart an already-running Codex session to discover newly added MCP tools.
Use `/mcp` inside Codex to inspect its active servers.

## Using PMM from Codex

Example requests:

- “Read the latest PMM events and cite event IDs for the relevant history.”
- “Fetch PMM event 123, including its recorded relationship metadata.”
- “Ask PMM to consider this task using pmm_turn: …”

| Tool | Behavior |
| --- | --- |
| `pmm_status` | Read ledger connectivity, latest event ID, and configured PMM model. |
| `pmm_read_events` | Read up to 100 event previews. Omit `after_id` for recent history; start at 0 and use `next_after_id` to page forward. |
| `pmm_get_event` | Fetch a full source event, including metadata and chain hashes. |
| `pmm_turn` | Invoke the configured PMM model, recording the prompt, terminal result, and normal derived events through PMM's runtime. |

Previews truncate content at 2,000 characters and omit metadata. Full event
reads can be large. Paging is over append-only history, not a semantic search
or a snapshot of current commitments. Recorded statements and relationships
are evidence of history, not proof of their truth or authority. Inspect source
metadata and subsequent events before drawing conclusions about current state.

A failed turn can still have recorded its input or failure event. Inspect the
returned `generation_failure` and ledger before retrying; the tool is not an
idempotent write. Separate PMM writers remain subject to the existing database
lease and fencing rules.

The implementation uses the supported
[Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
The official default tool timeout is 60 seconds; the launcher supplies the
longer timeout without editing the user's global configuration.
