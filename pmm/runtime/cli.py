# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/runtime/cli.py
from __future__ import annotations

import json
import os
import subprocess
from typing import Dict, Optional

from pmm.core.event_log import EventLog
from pmm.core.mirror import Mirror
from pmm.core.ledger_metrics import (
    compute_metrics,
)
from pmm.core.commitment_manager import CommitmentManager
from pmm.runtime.loop import RuntimeLoop
from pmm.core.meme_graph import MemeGraph
from pmm.core.semantic_extractor import (
    extract_claims,
    extract_commitments,
    extract_closures,
    extract_reflect,
)
from rich.console import Console
from rich.theme import Theme
from rich.table import Table
from datetime import datetime

# CLI Theme - Nord colors
CLI_THEME = Theme(
    {
        "header": "bold #88C0D0",  # Nord8 - Frost cyan
        "command": "bold #EBCB8B",  # Nord13 - Aurora yellow
        "number": "#EBCB8B",  # Nord13 - Aurora yellow
        "prompt": "dim #D8DEE9",  # Nord4 - Snow Storm
        "success": "bold #A3BE8C",  # Nord14 - Aurora green
        "error": "bold #BF616A",  # Nord11 - Aurora red
        "info": "#88C0D0",  # Nord8 - Frost cyan
    }
)

console = Console(theme=CLI_THEME)


def _export_chat_session(elog: EventLog, format: str = "markdown") -> str:
    """Export chat session to file. Returns filename."""
    from datetime import datetime

    # Get all user and assistant messages
    user_events = elog.read_by_kind("user_message")
    assistant_events = elog.read_by_kind("assistant_message")
    messages = sorted(user_events + assistant_events, key=lambda ev: int(ev["id"]))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if format == "markdown":
        filename = f"chat_export_{timestamp}.md"
        lines = [
            "# Chat Session Export\n",
            f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            f"**Total Messages:** {len(messages)}\n",
            "---\n",
        ]

        for msg in messages:
            kind = msg.get("kind")
            content = msg.get("content", "")
            ts = msg.get("ts", "")

            if kind == "user_message":
                lines.append("## 👤 User\n")
                lines.append(f"*{ts}*\n")
                lines.append(f"{content}\n\n")
            elif kind == "assistant_message":
                # Filter out internal markers
                visible_lines = []
                for ln in content.splitlines():
                    if (
                        extract_commitments([ln])
                        or extract_closures([ln])
                        or extract_reflect([ln]) is not None
                    ):
                        continue
                    try:
                        if extract_claims([ln]):
                            continue
                    except ValueError:
                        pass
                    visible_lines.append(ln)
                visible_content = "\n".join(visible_lines).strip()

                lines.append("## 🤖 Assistant\n")
                lines.append(f"*{ts}*\n")
                lines.append(f"{visible_content}\n\n")

        with open(filename, "w", encoding="utf-8") as f:
            f.writelines(lines)

    elif format == "json":
        filename = f"chat_export_{timestamp}.json"
        export_data = {
            "exported_at": datetime.now().isoformat(),
            "total_messages": len(messages),
            "messages": [],
        }

        for msg in messages:
            kind = msg.get("kind")
            content = msg.get("content", "")

            # Filter assistant messages
            if kind == "assistant_message":
                visible_lines = []
                for ln in content.splitlines():
                    if (
                        extract_commitments([ln])
                        or extract_closures([ln])
                        or extract_reflect([ln]) is not None
                    ):
                        continue
                    try:
                        if extract_claims([ln]):
                            continue
                    except ValueError:
                        pass
                    visible_lines.append(ln)
                content = "\n".join(visible_lines).strip()

            export_data["messages"].append(
                {
                    "role": "user" if kind == "user_message" else "assistant",
                    "timestamp": msg.get("ts", ""),
                    "content": content,
                }
            )

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

    return filename


def _format_replay_table(events: list[dict]) -> Table:
    """Format event log as a Rich table."""
    table = Table(
        show_header=True, header_style="header", border_style="prompt", expand=True
    )
    table.add_column("ID", style="number", width=6, no_wrap=True)
    table.add_column("Kind", style="info", width=20, no_wrap=True)
    table.add_column("Content", style="dim", no_wrap=False, overflow="fold")

    for event in events:
        event_id = str(event.get("id", ""))
        kind = event.get("kind", "")
        content = event.get("content", "")

        # Don't truncate - let Rich wrap the text
        table.add_row(event_id, kind, content)

    return table


def _gather_models() -> list[str]:
    models: list[str] = []
    try:
        result = subprocess.run(
            ["ollama", "list", "--json"], capture_output=True, text=True, check=True
        )
        models_data = json.loads(result.stdout) if result.stdout.strip() else []
        models.extend([m.get("name") for m in models_data if m.get("name")])
    except Exception:
        try:
            result = subprocess.run(
                ["ollama", "list"], capture_output=True, text=True, check=True
            )
            lines = [
                ln.strip() for ln in (result.stdout or "").splitlines() if ln.strip()
            ]
            if lines and lines[0].lower().startswith("name"):
                lines = lines[1:]
            models.extend([ln.split()[0] for ln in lines if ln])
        except Exception:
            pass

    if os.environ.get("OPENAI_API_KEY"):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            openai_models = [m.id for m in client.models.list()]
            models.extend([f"openai:{m}" for m in openai_models])
        except Exception:
            default_openai_model = (
                os.environ.get("PMM_OPENAI_MODEL")
                or os.environ.get("OPENAI_MODEL")
                or "gpt-4o-mini"
            )
            models.append(f"openai:{default_openai_model}")

    return models


def _resolve_model_selection(
    choice_raw: str, models: list[str]
) -> tuple[str, bool, str]:
    if not models:
        raise ValueError("No models available")
    selected: str | None = None
    if choice_raw.isdigit():
        idx = max(1, min(int(choice_raw), len(models)))
        selected = models[idx - 1]
    else:
        lowered = choice_raw.lower()
        for m in models:
            lowered_name = m.lower()
            if (
                lowered_name == lowered
                or lowered_name.startswith(lowered + ":")
                or lowered_name.startswith(lowered)
            ):
                selected = m
                break
        if selected is None:
            selected = models[0]
    use_openai = selected.startswith("openai:")
    model_name = selected.split(":", 1)[1] if use_openai else selected
    return selected, use_openai, model_name


def _instantiate_adapter(use_openai: bool, model_name: str):
    if use_openai:
        from pmm.adapters.openai_adapter import OpenAIAdapter

        return OpenAIAdapter(model=model_name)
    from pmm.adapters.ollama_adapter import OllamaAdapter

    return OllamaAdapter(model=model_name)


def _prompt_for_model_choice(models: list[str]) -> str | None:
    print("\nAvailable models:")
    for i, m in enumerate(models, 1):
        print(f"  {i}) {m}")
    choice = input(f"Choice [1-{len(models)}] (Enter to cancel): ").strip()
    return choice or None


def main() -> None:  # pragma: no cover - thin wrapper
    # Resolve canonical DB path with legacy fallback/migration
    import pathlib

    data_dir = pathlib.Path(".data/pmmdb")
    canonical = data_dir / "pmm.db"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    db_path = str(canonical)

    # Load .env if present (for OPENAI_API_KEY/OPENAI_MODEL etc.)
    try:  # optional dependency; safe if missing
        from dotenv import load_dotenv  # type: ignore

        load_dotenv()
    except Exception:
        pass

    # Interactive provider prompt
    console.print("\n🧠  [header]Persistent Mind Model[/header]\n")

    models = _gather_models()

    if not models:
        console.print(
            "[error]No models found. For Ollama, run 'ollama serve' and 'ollama pull <model>'.[/error]"
        )
        return

    # Model selection table
    model_table = Table(
        show_header=True,
        header_style="header",
        border_style="prompt",
        title="[info]Select a model to chat with[/info]",
    )
    model_table.add_column("#", style="number", width=4, justify="right")
    model_table.add_column("Model", style="info")

    for i, m in enumerate(models, 1):
        model_table.add_row(str(i), m)

    console.print(model_table)
    console.print()

    # Commands table
    commands_table = Table(
        show_header=True,
        header_style="header",
        border_style="prompt",
        title="[header]Commands[/header]",
    )
    commands_table.add_column("Command", style="command", width=40)
    commands_table.add_column("Description", style="dim")

    commands_table.add_row("/help", "Show this list of commands")
    commands_table.add_row("/replay", "Show last 50 events")
    commands_table.add_row("/metrics", "Show ledger metrics summary")
    commands_table.add_row("/diag", "Show last 5 diagnostic turns")
    commands_table.add_row("/goals", "Show open internal goals")
    commands_table.add_row("/rsm [id | diff <a> <b>]", "Show Recursive Self-Model")
    commands_table.add_row("/graph stats", "Show event graph stats")
    commands_table.add_row("/graph thread <CID>", "Show thread for a commitment")
    commands_table.add_row(
        "/config retrieval fixed limit <N>", "Set fixed window limit"
    )
    commands_table.add_row("/rebuild-fast", "Verify fast RSM rebuild matches full")
    commands_table.add_row("/pm", "Admin commands (type '/pm' for help)")
    commands_table.add_row("/raw", "Show last assistant message with markers")
    commands_table.add_row("/model", "Switch to a different model")
    commands_table.add_row("/export [md|json]", "Export chat session to file")
    commands_table.add_row("/exit", "Quit")

    console.print(commands_table)
    console.print()
    # Brief autonomy note about idle optimization (deterministic behavior)
    console.print(
        "[prompt]Note: Autonomy may auto-close stale commitments when they have been idle longer than the configured threshold (and have no exec binding).[/prompt]"
    )
    choice_raw = input(f"Choice [1-{len(models)}]: ").strip()
    # Allow immediate exit at selection prompt
    if choice_raw.lower() in {"/exit", "exit", "quit"}:
        return
    # Default to first entry on blank
    if not choice_raw:
        choice_raw = "1"
    selected, use_openai, model_name = _resolve_model_selection(choice_raw, models)

    console.print(f"\n[success]→ Using model: {selected}[/success]\n")
    console.print("[prompt]Type '/exit' to quit.[/prompt]\n")

    elog = EventLog(db_path)
    adapter = _instantiate_adapter(use_openai, model_name)
    loop = RuntimeLoop(eventlog=elog, adapter=adapter, replay=False)

    try:
        while True:
            user = input("[User Prompt]: ")
            if user is None:
                break
            if user.strip().lower() in {"/exit", "exit", "quit"}:
                break
            # Capture last event id before turn (for simple per-turn badge)
            _tail_before = elog.read_tail(1)
            _last_before_id = int(_tail_before[-1]["id"]) if _tail_before else 0
            # In-session commands (no CLI flags)
            raw_cmd = user.strip()
            cmd = raw_cmd.lower()
            if cmd == "/help":
                # Show commands table
                help_table = Table(
                    show_header=True,
                    header_style="header",
                    border_style="prompt",
                    title="[header]Commands[/header]",
                )
                help_table.add_column("Command", style="command", width=40)
                help_table.add_column("Description", style="dim")

                help_table.add_row("/help", "Show this list of commands")
                help_table.add_row("/replay", "Show last 50 events")
                help_table.add_row("/metrics", "Show ledger metrics summary")
                help_table.add_row("/diag", "Show last 5 diagnostic turns")
                help_table.add_row("/goals", "Show open internal goals")
                help_table.add_row(
                    "/rsm [id | diff <a> <b>]", "Show Recursive Self-Model"
                )
                help_table.add_row("/graph stats", "Show event graph stats")
                help_table.add_row(
                    "/graph thread <CID>", "Show thread for a commitment"
                )
                help_table.add_row(
                    "/config retrieval fixed limit <N>", "Set fixed window limit"
                )
                help_table.add_row(
                    "/rebuild-fast", "Verify fast RSM rebuild matches full"
                )
                help_table.add_row("/pm", "Admin commands (type '/pm' for help)")
                help_table.add_row("/raw", "Show last assistant message with markers")
                help_table.add_row("/model", "Switch to a different model")
                help_table.add_row("/export [md|json]", "Export chat session to file")
                help_table.add_row("/exit", "Quit")

                console.print(help_table)
                continue
            if cmd.startswith("/rsm"):
                output = handle_rsm_command(raw_cmd, elog)
                if output:
                    console.print(output)
                continue
            if cmd == "/pm" or cmd.startswith("/pm "):
                out = handle_pm_command(raw_cmd, elog)
                if out:
                    print(out)
                continue
            if cmd.startswith("/graph"):
                out = handle_graph_command(raw_cmd, elog)
                if out:
                    print(out)
                continue
            if cmd.startswith("/config "):
                out = handle_config_command(raw_cmd, elog)
                if out:
                    print(out)
                continue
            if cmd == "/rebuild-fast":
                out = handle_rebuild_fast(elog)
                if out:
                    print(out)
                continue
            if cmd in {"/goals"}:
                console.print(handle_goals_command(elog))
                continue
            if cmd in {"/replay"}:
                events = elog.read_tail(50)
                if events:
                    table = _format_replay_table(events)
                    console.print(table)
                else:
                    console.print("[prompt]No events in ledger.[/prompt]")
                continue
            if cmd in {"/metrics"}:
                from pmm.core.ledger_metrics import format_metrics_tables

                tracker = loop.tracker if hasattr(loop, "tracker") else None
                if tracker:
                    tracker.rebuild()
                metrics = compute_metrics(db_path, tracker)
                tables = format_metrics_tables(metrics)
                for table in tables:
                    console.print(table)
                    console.print()
                continue
            if cmd in {"/diag"}:
                events = [
                    e for e in elog.read_tail(200) if e.get("kind") == "metrics_turn"
                ][-5:]
                for e in events:
                    console.print(
                        f"[{e['id']}] {e.get('ts', '')} metrics_turn | {e['content']}"
                    )
                continue
            if cmd in {"/raw"}:
                # Show last assistant message exactly as logged (including markers)
                tail = [
                    e
                    for e in elog.read_tail(200)
                    if e.get("kind") == "assistant_message"
                ]
                if tail:
                    console.print(f"Assistant (raw)> {tail[-1].get('content') or ''}")
                else:
                    console.print("[prompt]No assistant messages yet.[/prompt]")
                continue
            if cmd.startswith("/model"):
                out = handle_model_command(raw_cmd, loop)
                if out:
                    print(out)
                continue
            if cmd.startswith("/export"):
                # Parse format (default to markdown)
                parts = raw_cmd.split()
                export_format = "markdown"
                if len(parts) > 1:
                    fmt = parts[1].lower()
                    if fmt in {"json", "md", "markdown"}:
                        export_format = "json" if fmt == "json" else "markdown"

                try:
                    filename = _export_chat_session(elog, export_format)
                    console.print(f"[success]✓ Chat exported to: {filename}[/success]")
                except Exception as e:
                    console.print(f"[error]Export failed: {e}[/error]")
                continue

            events = loop.run_turn(user)
            ai_msgs = [e for e in events if e.get("kind") == "assistant_message"]
            if ai_msgs:
                content = ai_msgs[-1].get("content") or ""
                # Hide marker lines for conversational display
                visible_lines = []
                for ln in content.splitlines():
                    if (
                        extract_commitments([ln])
                        or extract_closures([ln])
                        or extract_reflect([ln]) is not None
                    ):
                        continue
                    try:
                        if extract_claims([ln]):
                            continue
                    except ValueError:
                        pass
                    visible_lines.append(ln)
                assistant_output = "\n".join(visible_lines).strip()
                if assistant_output:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    console.print(f"\n[prompt]{timestamp}[/prompt]")
                    console.print(f"[info][Assistant]:[/info] {assistant_output}\n")
                # Optional badge: per-turn counts (derived deterministically from ledger)
                # Count claims from this assistant message
                try:
                    claims = len(extract_claims(content.splitlines()))
                except ValueError:
                    claims = 0
                # Count commitment opens/closes since last_before_id
                turn_events = [
                    e for e in events if int(e.get("id", 0)) > _last_before_id
                ]
                opened = sum(
                    1 for e in turn_events if e.get("kind") == "commitment_open"
                )
                closed = sum(
                    1 for e in turn_events if e.get("kind") == "commitment_close"
                )
                if opened or closed or claims:
                    console.print(
                        f"[prompt]({opened} opened, {closed} closed, {claims} claims)[/prompt]"
                    )
    except KeyboardInterrupt:
        return


if __name__ == "__main__":  # pragma: no cover
    main()


def handle_model_command(command: str, loop: RuntimeLoop) -> Optional[str]:
    parts = command.strip().split(maxsplit=1)
    if not parts or parts[0].lower() != "/model":
        return None

    models = _gather_models()
    if not models:
        return (
            "No models found. For Ollama, run 'ollama serve' and 'ollama pull <model>'."
        )

    remainder = parts[1].strip() if len(parts) > 1 else ""
    if not remainder or remainder.lower() in {"list", "ls"}:
        remainder = _prompt_for_model_choice(models)
        if remainder is None:
            return "Model change canceled."

    selected, use_openai, model_name = _resolve_model_selection(remainder, models)
    loop.adapter = _instantiate_adapter(use_openai, model_name)
    return f"Switched to model: {selected}"


def handle_rsm_command(command: str, eventlog: EventLog) -> Optional[str]:
    parts = command.strip().split()
    if not parts or parts[0].lower() != "/rsm":
        return None

    mirror = Mirror(eventlog, enable_rsm=True, listen=False)
    try:
        args = parts[1:]
        if not args:
            latest_id = _latest_event_id(eventlog)
            snapshot = mirror.rsm_snapshot()
            return _format_snapshot(snapshot, latest_id, current=True)
        if len(args) == 1:
            event_id = int(args[0])
            if event_id < 0:
                return "Event ids must be non-negative integers."
            historical = mirror._rebuild_up_to(event_id).rsm_snapshot()
            return _format_snapshot(historical, event_id, current=False)
        if len(args) == 3 and args[0].lower() == "diff":
            start = int(args[1])
            end = int(args[2])
            if start < 0 or end < 0:
                return "Event ids must be non-negative integers."
            diff = mirror.diff_rsm(start, end)
            diff_payload = {
                "from_event": start,
                "to_event": end,
                "tendencies_delta": diff["tendencies_delta"],
                "gaps_added": diff["gaps_added"],
                "gaps_resolved": diff["gaps_resolved"],
            }
            return _format_diff(diff_payload)
        return "Usage: /rsm [id | diff <a> <b>]"
    except ValueError:
        return "Event ids must be integers."


def handle_pm_command(command: str, eventlog: EventLog) -> Optional[str]:
    parts = command.strip().split()
    if not parts or parts[0].lower() != "/pm":
        return None
    # Help root
    if len(parts) == 1 or parts[1].lower() in {"help", "?"}:
        return (
            "Admin topics: graph | retrieval | checkpoint | rebuild | config | ctl\n"
            "Examples:\n"
            "  /pm graph stats\n  /pm graph thread <CID>\n"
            "  /pm retrieval config fixed limit 7\n  /pm retrieval last\n"
            "  /pm ctl backfill threads 400\n"
            "  /pm checkpoint\n  /pm rebuild fast\n"
            "  /pm config autonomy reflection_interval=12 commitment_staleness=25"
        )
    topic = parts[1].lower()
    rest = parts[2:]
    if topic == "graph":
        # Reuse existing handler; print gentle hint
        output = handle_graph_command("/graph " + " ".join(rest), eventlog)
        if output:
            return output + "\n(hint: /graph is an alias; prefer /pm graph …)"
        return "Usage: /pm graph stats | thread <CID>"
    if topic == "ctl":
        if rest[:2] == ["backfill", "threads"]:
            try:
                n = int(rest[2]) if len(rest) >= 3 else 400
            except ValueError:
                return "Batch size must be an integer"
            if _policy_forbids(eventlog, source="cli", kind="concept_bind_thread"):
                return "Forbidden by policy."
            return _handle_ctl_thread_backfill(eventlog, n)
        return "Usage: /pm ctl backfill threads [batch]"
    if topic == "rebuild":
        if rest[:1] == ["fast"] and len(rest) == 1:
            out = handle_rebuild_fast(eventlog)
            if out:
                return (
                    out + "\n(hint: /rebuild-fast is an alias; prefer /pm rebuild fast)"
                )
            return "Fast rebuild not available"
        return "Usage: /pm rebuild fast"
    if topic == "checkpoint":
        # Deny before attempting if policy forbids CLI writing checkpoint_manifest
        if _policy_forbids(eventlog, source="cli", kind="checkpoint_manifest"):
            return "Forbidden by policy."
        return _handle_checkpoint(eventlog)
    if topic == "retrieval":
        # Map retrieval config fixed to existing config handler
        if rest[:2] == ["config", "fixed"]:
            # e.g., /pm retrieval config fixed limit 7
            mapped = ["/config", "retrieval", "fixed"] + rest[2:]
            return handle_config_command(" ".join(mapped), eventlog)
        if rest[:2] == ["config", "vector"]:
            # /pm retrieval config vector limit <N> model <name> dims <D> quant <int8|none>
            args = rest[2:]
            cfg = {
                "type": "retrieval",
                "strategy": "vector",
                "limit": 5,
                "model": "hash64",
                "dims": 64,
                "quant": "none",
            }
            i = 0
            while i < len(args):
                key = args[i]
                val = args[i + 1] if i + 1 < len(args) else None
                if key == "limit" and val is not None:
                    try:
                        cfg["limit"] = int(val)
                    except ValueError:
                        return "Limit must be an integer"
                    i += 2
                    continue
                if key == "model" and val is not None:
                    cfg["model"] = val
                    i += 2
                    continue
                if key == "dims" and val is not None:
                    try:
                        cfg["dims"] = int(val)
                    except ValueError:
                        return "Dims must be an integer"
                    i += 2
                    continue
                if key == "quant" and val is not None:
                    cfg["quant"] = val
                    i += 2
                    continue
                i += 1
            current = _last_retrieval_config(eventlog)
            if current == cfg:
                return "No change (idempotent)"
            if _policy_forbids(eventlog, source="cli", kind="config"):
                return "Forbidden by policy."
            eventlog.append(
                kind="config",
                content=json.dumps(cfg, separators=(",", ":")),
                meta={"source": "cli"},
            )
            return f"Retrieval config updated: vector limit={cfg['limit']} model={cfg['model']} dims={cfg['dims']}"
        if rest[:1] == ["index"] and len(rest) >= 2 and rest[1] == "backfill":
            try:
                n = int(rest[2]) if len(rest) >= 3 else 100
            except ValueError:
                return "Backfill N must be an integer"
            try:
                return _handle_retrieval_backfill(eventlog, n)
            except PermissionError:
                return "Forbidden by policy."
        if rest == ["status"]:
            return _handle_retrieval_status(eventlog)
        if len(rest) == 2 and rest[0] == "verify" and rest[1].isdigit():
            turn_id = int(rest[1])
            return _handle_retrieval_verify(eventlog, turn_id)
        if rest == ["last"]:
            tail = [
                e
                for e in eventlog.read_tail(200)
                if e.get("kind") == "retrieval_selection"
            ]
            if not tail:
                return "No retrieval_selection recorded yet."
            ev = tail[-1]
            try:
                data = json.loads(ev.get("content") or "{}")
            except Exception:
                data = {}
            return f"retrieval_selection turn_id={data.get('turn_id')} selected={data.get('selected')} scores={data.get('scores')}"
        return "Usage: /pm retrieval config fixed limit <N> | config vector … | last | index backfill <N> | status | verify <turn_id>"
    if topic == "config":
        # autonomy thresholds: key=value pairs
        if rest and rest[0].lower() == "autonomy":
            args = rest[1:]
            if not args:
                return (
                    "Usage: /pm config autonomy key=value …\n"
                    "Keys: reflection_interval, summary_interval, commitment_staleness, commitment_auto_close"
                )
            updates: Dict[str, int] = {}
            for token in args:
                if "=" not in token:
                    continue
                k, v = token.split("=", 1)
                k = k.strip()
                try:
                    updates[k] = int(v)
                except ValueError:
                    return f"Invalid integer for {k}"
            if not updates:
                return "No valid keys provided"
            # Merge with last autonomy_thresholds; idempotent write only if changed
            current = _last_autonomy_cfg(eventlog)
            desired = {"type": "autonomy_thresholds"}
            if isinstance(current, dict):
                desired.update(current)
            desired.update(updates)
            # If no changes, exit
            if current:
                unchanged = True
                for k, v in updates.items():
                    if int(current.get(k, -9999)) != v:
                        unchanged = False
                        break
                if unchanged:
                    return "No change (idempotent)"
            eventlog.append(
                kind="config",
                content=json.dumps(desired, separators=(",", ":")),
                meta={"source": "cli"},
            )
            return "Autonomy thresholds updated"
        return "Usage: /pm config autonomy key=value …"
    return "Unknown /pm topic. Try '/pm' for help."


def _last_autonomy_cfg(eventlog: EventLog) -> Optional[Dict]:
    for ev in eventlog.read_by_kind("config", reverse=True):
        try:
            data = json.loads(ev.get("content") or "{}")
        except Exception:
            continue
        if isinstance(data, dict) and data.get("type") == "autonomy_thresholds":
            return data
    return None


def _policy_forbids(eventlog: EventLog, *, source: str, kind: str) -> bool:
    for ev in eventlog.read_by_kind("config", reverse=True):
        try:
            data = json.loads(ev.get("content") or "{}")
        except Exception:
            continue
        if isinstance(data, dict) and data.get("type") == "policy":
            fs = data.get("forbid_sources") or {}
            kinds = fs.get(source)
            return isinstance(kinds, list) and kind in kinds
    return False


def _message_events(events):
    return [e for e in events if e.get("kind") in ("user_message", "assistant_message")]


def _embedding_map(events, *, model: str, dims: int):
    out = {}
    for e in events:
        if e.get("kind") != "embedding_add":
            continue
        try:
            data = json.loads(e.get("content") or "{}")
        except Exception:
            continue
        if (
            isinstance(data, dict)
            and data.get("model") == model
            and int(data.get("dims", 0)) == int(dims)
        ):
            out[int(data.get("event_id", 0))] = data
    return out


def _handle_retrieval_backfill(eventlog: EventLog, n: int) -> str:
    cfg = _last_retrieval_config(eventlog) or {}
    if cfg.get("strategy") != "vector":
        return "Retrieval strategy is not 'vector'"
    model = str(cfg.get("model", "hash64"))
    dims = int(cfg.get("dims", 64))
    window = max(1, int(max(n * 4, 500)))
    events = eventlog.read_tail(window)
    msgs = _message_events(events)[-max(1, n) :]
    existing = _embedding_map(events, model=model, dims=dims)
    from pmm.retrieval.vector import build_embedding_content

    appended = 0
    for m in msgs:
        eid = int(m.get("id", 0))
        if eid in existing:
            continue
        content = m.get("content") or ""
        payload = build_embedding_content(
            event_id=eid, text=content, model=model, dims=dims
        )
        eventlog.append(kind="embedding_add", content=payload, meta={"source": "cli"})
        appended += 1
    return f"Backfill appended: {appended}"


def _handle_retrieval_status(eventlog: EventLog) -> str:
    cfg = _last_retrieval_config(eventlog) or {}
    model = str(cfg.get("model", "hash64"))
    dims = int(cfg.get("dims", 64))
    msgs = eventlog.read_by_kind("user_message") + eventlog.read_by_kind(
        "assistant_message"
    )
    emb_events = eventlog.read_by_kind("embedding_add")
    embs = _embedding_map(emb_events, model=model, dims=dims)
    return f"messages:{len(msgs)} embeddings:{len(embs)} model:{model} dims:{dims}"


def _handle_retrieval_verify(eventlog: EventLog, turn_id: int) -> str:
    # Find the retrieval_selection for this turn
    target = None
    for e in eventlog.read_by_kind("retrieval_selection", reverse=True, limit=500):
        try:
            data = json.loads(e.get("content") or "{}")
        except Exception:
            continue
        if int(data.get("turn_id", 0)) == int(turn_id):
            target = data
            break
    if target is None:
        return "No retrieval_selection for that turn"

    cfg = _last_retrieval_config(eventlog) or {}
    model = str(cfg.get("model", "hash64"))
    dims = int(cfg.get("dims", 64))
    selected = target.get("selected") or []

    # Here we would recompute digest; for brevity, report selection
    return f"retrieval_selection turn_id={turn_id} selected={selected} model={model} dims={dims}"


def _handle_ctl_thread_backfill(eventlog: EventLog, batch: int) -> str:
    """Backfill concept->CID bindings using Indexer."""
    from pmm.runtime.indexer import Indexer

    idx = Indexer(eventlog)
    emitted = idx.backfill_concept_thread_bindings(batch=batch)
    return f"concept_bind_thread emitted: {emitted}"


def _handle_checkpoint(eventlog: EventLog) -> str:
    last_summary = next(
        iter(eventlog.read_by_kind("summary_update", reverse=True, limit=1)), None
    )
    if not last_summary:
        return "No summary_update found to anchor checkpoint."
    up_to = int(last_summary.get("id", 0))
    events = eventlog.read_up_to(up_to)
    if up_to > 100000:
        return "Checkpoint creation blocked: ledger too large for unbounded hash. Use segmented checkpoints."
    # Compute root hash over hash sequence up to anchor
    hashes = [e.get("hash") or "" for e in events if int(e.get("id", 0)) <= up_to]
    root_blob = json.dumps(hashes, separators=(",", ":"))
    import hashlib as _hl

    digest = _hl.sha256(root_blob.encode("utf-8")).hexdigest()
    # Idempotent: check last manifest
    last_manifest = next(
        iter(eventlog.read_by_kind("checkpoint_manifest", reverse=True, limit=1)),
        None,
    )
    if last_manifest:
        try:
            data = json.loads(last_manifest.get("content") or "{}")
        except Exception:
            data = {}
        if int(data.get("up_to_id", 0)) == up_to and data.get("root_hash") == digest:
            return "No change (idempotent)"
    content = json.dumps(
        {
            "up_to_id": up_to,
            "covers": ["rsm_state", "open_commitments"],
            "root_hash": digest,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    eventlog.append(kind="checkpoint_manifest", content=content, meta={"source": "cli"})
    return f"Checkpoint manifest appended at up_to_id={up_to}"


def handle_graph_command(command: str, eventlog: EventLog) -> Optional[str]:
    parts = command.strip().split()
    if not parts or parts[0].lower() != "/graph":
        return None
    # Large-ledger guardrail: block unbounded graph stats/rebuilds without explicit consent
    # by limiting the rebuild to tracked kinds only (already bounded) and refusing if the
    # ledger is extremely large.
    latest_id = _latest_event_id(eventlog)
    if latest_id > 100000:
        return (
            "Graph stats disabled on large ledgers; use checkpoints or filtered tools."
        )
    mg = MemeGraph(eventlog)
    tracked_events = []
    for k in MemeGraph.TRACKED_KINDS:
        tracked_events.extend(eventlog.read_by_kind(k))
    tracked_events.sort(key=lambda ev: int(ev["id"]))
    mg.rebuild(tracked_events)
    if len(parts) == 2 and parts[1].lower() == "stats":
        stats = mg.graph_stats()
        lines = [
            f"nodes: {stats['nodes']}",
            f"edges: {stats['edges']}",
            "counts_by_kind:",
        ]
        for k in sorted(stats["counts_by_kind"].keys()):
            lines.append(f"  {k}: {stats['counts_by_kind'][k]}")
        return "\n".join(lines)
    if len(parts) == 3 and parts[1].lower() == "thread":
        cid = parts[2]
        thread = mg.thread_for_cid(cid)
        if not thread:
            return f"No thread found for CID {cid}"
        lines = [f"Thread for {cid}:"]
        for eid in thread:
            ev = eventlog.get(eid)
            if not ev:
                continue
            kind = ev.get("kind")
            content = (ev.get("content") or "").splitlines()[0][:80]
            lines.append(f"[{eid}] {kind} | {content}")
        return "\n".join(lines)
    if len(parts) == 3 and parts[1].lower() == "explain":
        cid = parts[2]
        sub_ids = mg.subgraph_for_cid(cid)
        if not sub_ids:
            return f"No subgraph found for CID {cid}"
        lines = [f"Explanation for {cid}:"]
        for eid in sub_ids:
            ev = eventlog.get(eid)
            if not ev:
                continue
            kind = ev.get("kind")
            content = (ev.get("content") or "").splitlines()[0][:80]
            lines.append(f"[{eid}] {kind} | {content}")
        return "\n".join(lines)
    return "Usage: /graph stats | /graph thread <CID> | /graph explain <CID>"


def _last_retrieval_config(eventlog: EventLog) -> Optional[Dict]:
    for ev in eventlog.read_by_kind("config", reverse=True):
        try:
            data = json.loads(ev.get("content") or "{}")
        except Exception:
            continue
        if isinstance(data, dict) and data.get("type") == "retrieval":
            return data
    return None


def handle_config_command(command: str, eventlog: EventLog) -> Optional[str]:
    parts = command.strip().split()
    if parts[:3] != ["/config", "retrieval", "fixed"]:
        return "Usage: /config retrieval fixed limit <N>"
    if len(parts) != 6 or parts[3] != "limit":
        return "Usage: /config retrieval fixed limit <N>"
    try:
        limit = int(parts[5])
    except ValueError:
        return "Limit must be an integer"
    if limit <= 0:
        return "Limit must be positive"
    current = _last_retrieval_config(eventlog)
    desired = {"type": "retrieval", "strategy": "fixed", "limit": limit}
    if current == desired:
        return "No change (idempotent)"
    eventlog.append(
        kind="config", content=json.dumps(desired, separators=(",", ":")), meta={}
    )
    return f"Retrieval config updated: limit={limit}"


def handle_rebuild_fast(eventlog: EventLog) -> Optional[str]:
    mirror_full = Mirror(eventlog, enable_rsm=True, listen=False)
    snap_full = mirror_full.rsm_snapshot()

    # Simulate fast rebuild by constructing a fresh mirror and calling fast path.
    mirror_fast = Mirror(eventlog, enable_rsm=True, listen=False)
    try:
        mirror_fast.rebuild_fast()
        snap_fast = mirror_fast.rsm_snapshot()
        return (
            "Fast rebuild identical"
            if snap_fast == snap_full
            else "Fast rebuild differs"
        )
    except Exception:
        return "Fast rebuild not available"


def handle_goals_command(eventlog: EventLog) -> str:
    manager = CommitmentManager(eventlog)
    open_internal = manager.get_open_commitments(origin="autonomy_kernel")

    closed_count = sum(
        1
        for event in eventlog.read_by_kind("commitment_close")
        if (event.get("meta") or {}).get("origin") == "autonomy_kernel"
    )

    if not open_internal:
        return f"No open internal goals. {closed_count} closed."

    lines = [f"Internal goals ({len(open_internal)} open, {closed_count} closed):"]
    for event in open_internal:
        meta = event.get("meta") or {}
        cid = meta.get("cid", "unknown")
        goal = meta.get("goal", "unknown")
        reason = meta.get("reason")
        detail = f"{cid} | goal: {goal}"
        if reason:
            detail += f" | reason: {reason}"
        lines.append(detail)
    return "\n".join(lines)


def _latest_event_id(eventlog: EventLog) -> int:
    tail = eventlog.read_tail(1)
    return int(tail[-1]["id"]) if tail else 0


def _format_snapshot(
    snapshot: Dict[str, object], event_id: int, *, current: bool
) -> str:
    header = (
        "RSM Snapshot (current ledger)"
        if current
        else f"RSM Snapshot (event {event_id})"
    )
    lines = [header, "  Behavioral Tendencies:"]
    tendencies = snapshot.get("behavioral_tendencies", {}) or {}
    if tendencies:
        for key in sorted(tendencies):
            lines.append(f"    {key:<{_COLUMN_WIDTH}} {tendencies[key]}")
    else:
        lines.append("    (none)")

    gaps = snapshot.get("knowledge_gaps", []) or []
    gap_text = ", ".join(sorted(gaps)) if gaps else "(none)"
    lines.append(f"  Knowledge Gaps:        {gap_text}")

    meta_patterns = snapshot.get("interaction_meta_patterns", []) or []
    meta_text = ", ".join(sorted(meta_patterns)) if meta_patterns else "(none)"
    lines.append(f"  Interaction Patterns:  {meta_text}")
    return "\n".join(lines)


def _format_diff(diff: Dict[str, object]) -> str:
    header = f"RSM Diff ({diff['from_event']} -> {diff['to_event']})"
    lines = [header, "  Tendencies Delta:"]
    delta = diff.get("tendencies_delta", {}) or {}
    if delta:
        for key in sorted(delta):
            lines.append(f"    {key:<{_COLUMN_WIDTH}} {delta[key]:+d}")
    else:
        lines.append("    (none)")
    gaps_added = diff.get("gaps_added", []) or []
    gaps_resolved = diff.get("gaps_resolved", []) or []
    added_text = ", ".join(sorted(gaps_added)) if gaps_added else "(none)"
    resolved_text = ", ".join(sorted(gaps_resolved)) if gaps_resolved else "(none)"
    lines.append(f"  Gaps Added:           {added_text}")
    lines.append(f"  Gaps Resolved:        {resolved_text}")
    return "\n".join(lines)


RSM_HELP_TEXT = "  /rsm [id | diff <a> <b>] - show Recursive Self-Model (includes stability, adaptability, instantiation)"
_COLUMN_WIDTH = 24
