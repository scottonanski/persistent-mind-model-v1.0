# Path: pmm/runtime/cli.py
from __future__ import annotations

import json
import os
import subprocess
from typing import Dict, Optional

from pmm.core.event_log import EventLog
from pmm.core.ledger_mirror import LedgerMirror
from pmm.core.ledger_metrics import (
    compute_metrics,
    format_metrics_human,
)
from pmm.core.commitment_manager import CommitmentManager
from pmm.runtime.loop import RuntimeLoop
from pmm.runtime.replay_narrator import narrate


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
    print("\n🧠  Persistent Mind Model")
    print("────────────────────────────")
    print("Select a model to chat with:\n")

    # Gather available models from Ollama
    models: list[str] = []
    try:
        # Prefer JSON list
        result = subprocess.run(
            ["ollama", "list", "--json"], capture_output=True, text=True, check=True
        )
        models_data = json.loads(result.stdout) if result.stdout.strip() else []
        models.extend([m.get("name") for m in models_data if m.get("name")])
    except Exception:
        # Fallback to table parsing
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

    # OpenAI entry if API key is present
    if os.environ.get("OPENAI_API_KEY"):
        default_openai_model = (
            os.environ.get("PMM_OPENAI_MODEL")
            or os.environ.get("OPENAI_MODEL")
            or "gpt-4o-mini"
        )
        models.append(f"openai:{default_openai_model}")

    if not models:
        print(
            "No models found. For Ollama, run 'ollama serve' and 'ollama pull <model>'."
        )
        return

    for i, m in enumerate(models, 1):
        print(f"  {i}) {m}")
    print("────────────────────────────")
    print("Commands:")
    print("  /replay   Show last 50 events")
    print("  /metrics  Show ledger metrics summary")
    print("  /diag     Show last 5 diagnostic turns")
    print("  /goals    Show open internal goals")
    print(RSM_HELP_TEXT)
    print("  /exit     Quit")
    print("────────────────────────────")
    # Brief autonomy note about idle optimization (deterministic behavior)
    print(
        "Note: Autonomy auto-closes stale commitments when >2 are open and staleness exceeds the threshold."
    )
    choice_raw = input(f"Choice [1-{len(models)}]: ").strip()
    # Allow immediate exit at selection prompt
    if choice_raw.lower() in {"/exit", "exit", "quit"}:
        return
    # Default to first entry on blank
    if not choice_raw:
        choice_raw = "1"
    selected = None
    # Try numeric selection first
    if choice_raw.isdigit():
        idx = max(1, min(int(choice_raw), len(models)))
        selected = models[idx - 1]
    else:
        # Try to match by name/prefix (e.g., "openai")
        lowered = choice_raw.lower()
        for m in models:
            if (
                m.lower() == lowered
                or m.lower().startswith(lowered + ":")
                or m.lower().startswith(lowered)
            ):
                selected = m
                break
        if selected is None:
            # Fallback
            selected = models[0]

    use_openai = selected.startswith("openai:")
    model_name = selected.split(":", 1)[1] if use_openai else selected

    print(f"\n→ Using model: {selected}\n")
    print("Type '/exit' to quit.\n")

    elog = EventLog(db_path)
    if use_openai:
        from pmm.adapters.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter(model=model_name)
    else:
        from pmm.adapters.ollama_adapter import OllamaAdapter

        adapter = OllamaAdapter(model=model_name)
    loop = RuntimeLoop(eventlog=elog, adapter=adapter, replay=False)

    try:
        while True:
            user = input("You> ")
            if user is None:
                break
            if user.strip().lower() in {"/exit", "exit", "quit"}:
                break
            # In-session commands (no CLI flags)
            raw_cmd = user.strip()
            cmd = raw_cmd.lower()
            if cmd.startswith("/rsm"):
                output = handle_rsm_command(raw_cmd, elog)
                if output:
                    print(output)
                continue
            if cmd in {"/goals"}:
                print(handle_goals_command(elog))
                continue
            if cmd in {"/replay"}:
                print(narrate(elog, limit=50))
                continue
            if cmd in {"/metrics"}:
                tracker = loop.tracker if hasattr(loop, "tracker") else None
                if tracker:
                    tracker.rebuild()  # Rebuild from ledger on CLI load
                print(format_metrics_human(compute_metrics(db_path, tracker)))
                continue
            if cmd in {"/diag"}:
                events = [
                    e for e in elog.read_tail(200) if e.get("kind") == "metrics_turn"
                ][-5:]
                for e in events:
                    print(
                        f"[{e['id']}] {e.get('ts', '')} metrics_turn | {e['content']}"
                    )
                continue
            events = loop.run_turn(user)
            ai_msgs = [e for e in events if e.get("kind") == "assistant_message"]
            if ai_msgs:
                content = ai_msgs[-1].get("content") or ""
                out_lines = []
                for ln in content.splitlines():
                    if ln.startswith("COMMIT:"):
                        # Show the remainder of the line after the marker
                        remainder = ln.split(":", 1)[1].strip()
                        if remainder:
                            out_lines.append(remainder)
                        # Skip empty-only commit lines
                        continue
                    out_lines.append(ln)
                assistant_output = "\n".join(out_lines)
                print(f"Assistant> {assistant_output}")
    except KeyboardInterrupt:
        return


if __name__ == "__main__":  # pragma: no cover
    main()


def handle_rsm_command(command: str, eventlog: EventLog) -> Optional[str]:
    parts = command.strip().split()
    if not parts or parts[0].lower() != "/rsm":
        return None

    mirror = LedgerMirror(eventlog, listen=False)
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


def handle_goals_command(eventlog: EventLog) -> str:
    manager = CommitmentManager(eventlog)
    open_internal = manager.get_open_commitments(origin="autonomy_kernel")

    closed_count = sum(
        1
        for event in eventlog.read_all()
        if event.get("kind") == "commitment_close"
        and (event.get("meta") or {}).get("origin") == "autonomy_kernel"
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
