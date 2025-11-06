from __future__ import annotations

import json
import os
import subprocess
from typing import Dict, Optional

from pmm_v2.core.event_log import EventLog
from pmm_v2.core.ledger_mirror import LedgerMirror
from pmm_v2.core.ledger_metrics import (
    compute_metrics,
    format_metrics_human,
)
from pmm_v2.core.commitment_manager import CommitmentManager
from pmm_v2.runtime.loop import RuntimeLoop
from pmm_v2.runtime.replay_narrator import narrate


def main() -> None:  # pragma: no cover - thin wrapper
    db_path = "./pmm_v2.db"

    # Interactive provider prompt
    print("\n🧠  Persistent Mind Model v2")
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

    # OpenAI entries if API key is present
    if os.environ.get("OPENAI_API_KEY"):
        default_openai_model = os.environ.get("PMM_OPENAI_MODEL", "gpt-4o")
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
    choice = input(f"Choice [1-{len(models)}]: ").strip() or "1"
    try:
        selected = models[max(1, min(int(choice), len(models))) - 1]
    except Exception:
        selected = models[0]

    use_openai = selected.startswith("openai:")
    model_name = selected.split(":", 1)[1] if use_openai else selected

    print(f"\n→ Using model: {selected}\n")
    print("Type '/exit' to quit.\n")

    elog = EventLog(db_path)
    if use_openai:
        from pmm_v2.adapters.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter(model=model_name)
    else:
        from pmm_v2.adapters.ollama_adapter import OllamaAdapter

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
                rsm = loop.rsm if hasattr(loop, "rsm") else None
                print(format_metrics_human(compute_metrics(db_path, tracker, rsm=rsm)))
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
    from pmm_v2.runtime.commitment_manager import CommitmentManager

    cm = CommitmentManager(eventlog)
    goals = cm.get_open_commitments()
    internal_goals = [g for g in goals if g.get("meta", {}).get("source") == "autonomy_kernel"]

    # Count closed internal goals
    closed_count = sum(
        1 for e in eventlog.read_all()
        if e.get("kind") == "commitment_close" and e.get("meta", {}).get("source") == "autonomy_kernel"
    )

    if not internal_goals:
        return f"No open internal goals. {closed_count} closed."

    lines = [f"Open internal goals ({closed_count} closed):"]
    for g in internal_goals:
        lines.append(f"{g['meta']['cid']} | {g['meta']['goal']} | opened: {g['id']}")
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


RSM_HELP_TEXT = "  /rsm [id | diff <a> <b>] - show Recursive Self-Model"
_COLUMN_WIDTH = 24
