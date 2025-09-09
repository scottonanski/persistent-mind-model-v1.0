# pmm/cli/chat.py
from __future__ import annotations
import os
import sys
from pathlib import Path

from pmm.config import load_runtime_env
from pmm.storage.eventlog import EventLog
from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime, maybe_reflect as runtime_maybe_reflect


def main() -> None:
    env = load_runtime_env(".env")
    Path(env.db_path).parent.mkdir(parents=True, exist_ok=True)

    if env.provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set in environment (.env).", file=sys.stderr)
        sys.exit(2)

    log = EventLog(env.db_path)
    cfg = LLMConfig(
        provider=env.provider, model=env.model, embed_provider=None, embed_model=None
    )
    rt = Runtime(cfg, log)

    print(
        f"PMM ready ({env.provider}/{env.model}) — DB: {env.db_path}. Ctrl+C to exit.",
        flush=True,
    )
    try:
        while True:
            user = input("> ").strip()
            if not user:
                continue
            if user.lower() in {"exit", "quit", "/q"}:
                print("bye.")
                return
            reply = rt.handle_user(user)
            print(reply, flush=True)
            if env.reflect_enabled:
                try:
                    runtime_maybe_reflect(rt.eventlog, rt.cooldown)
                except Exception:
                    # best-effort reflection, never crash REPL
                    pass
    except (EOFError, KeyboardInterrupt):
        print("\nbye.")
        sys.exit(0)


if __name__ == "__main__":
    main()
