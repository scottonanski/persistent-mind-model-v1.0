from __future__ import annotations
import json
import subprocess

import os
from pmm_v2.adapters.factory import LLMFactory
from pmm_v2.core.event_log import EventLog
from pmm_v2.core.ledger_metrics import compute_metrics, format_metrics_human, append_metrics_if_delta
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
        result = subprocess.run(["ollama", "list", "--json"], capture_output=True, text=True, check=True)
        models_data = json.loads(result.stdout) if result.stdout.strip() else []
        models.extend([m.get("name") for m in models_data if m.get("name")])
    except Exception:
        # Fallback to table parsing
        try:
            result = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=True)
            lines = [ln.strip() for ln in (result.stdout or "").splitlines() if ln.strip()]
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
        print("No models found. For Ollama, run 'ollama serve' and 'ollama pull <model>'.")
        return

    for i, m in enumerate(models, 1):
        print(f"  {i}) {m}")
    print("────────────────────────────")
    print("Commands:")
    print("  /replay   Show last 50 events")
    print("  /metrics  Show ledger metrics summary")
    print("  /diag     Show last 5 diagnostic turns")
    print("  /exit     Quit")
    print("────────────────────────────")
    choice = (input(f"Choice [1-{len(models)}]: ").strip() or "1")
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
            cmd = user.strip().lower()
            if cmd in {"/replay"}:
                print(narrate(elog, limit=50))
                continue
            if cmd in {"/metrics"}:
                print(format_metrics_human(compute_metrics(db_path)))
                continue
            if cmd in {"/diag"}:
                events = [e for e in elog.read_tail(200) if e.get("kind") == "metrics_turn"][-5:]
                for e in events:
                    print(f"[{e['id']}] {e.get('ts', '')} metrics_turn | {e['content']}")
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
                print(f"Assistant> {'\n'.join(out_lines)}")
    except KeyboardInterrupt:
        return


if __name__ == "__main__":  # pragma: no cover
    main()
