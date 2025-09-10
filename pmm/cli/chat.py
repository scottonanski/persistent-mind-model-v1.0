# pmm/cli/chat.py
from __future__ import annotations
import os
import sys
from pathlib import Path

from pmm.config import load_runtime_env
from pmm.storage.eventlog import EventLog
from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime, maybe_reflect as runtime_maybe_reflect
from pmm.runtime.metrics_view import MetricsView
from pmm.storage.projection import build_identity


def should_print_identity_notice(events: list[dict]) -> bool:
    """Return True iff the most recent response event is the first one strictly after
    the most recent identity_adopt event.

    Logic: find last identity_adopt id (aid). Find the last two response ids in order
    of recency: [last, prev]. Print if aid exists and prev is missing or < aid, and aid <= last.
    """
    last_adopt_id = None
    resp_ids: list[int] = []
    for ev in reversed(events):
        k = ev.get("kind")
        if k == "identity_adopt" and last_adopt_id is None:
            last_adopt_id = int(ev.get("id") or 0)
        if k == "response":
            rid = ev.get("id")
            if isinstance(rid, int):
                resp_ids.append(rid)
        if last_adopt_id is not None and len(resp_ids) >= 2:
            break
    if last_adopt_id is None or not resp_ids:
        return False
    last_resp_id = resp_ids[0]
    prev_resp_id = resp_ids[1] if len(resp_ids) >= 2 else None
    if prev_resp_id is None or int(prev_resp_id) < int(last_adopt_id):
        return int(last_adopt_id) <= int(last_resp_id)
    return False


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
    # Load optional n-gram bans
    ngram_bans = None
    if env.ngram_ban_file:
        try:
            from pathlib import Path as _P

            p = _P(env.ngram_ban_file)
            if p.exists():
                ngram_bans = [
                    ln.strip()
                    for ln in p.read_text(encoding="utf-8").splitlines()
                    if ln.strip()
                ]
        except Exception:
            ngram_bans = None

    rt = Runtime(cfg, log, ngram_bans=ngram_bans)
    metrics_view = MetricsView()

    # Start background autonomy loop if configured
    if env.autonomy_interval and env.autonomy_interval > 0:
        rt.start_autonomy(env.autonomy_interval)

    print(
        f"PMM ready ({env.provider}/{env.model}) — DB: {env.db_path}. Ctrl+C to exit.",
        flush=True,
    )
    # Startup info banner for evolution mechanisms
    try:
        if env.autonomy_interval and env.autonomy_interval > 0:
            print(
                f"[INFO] Autonomy: ON — ticks every {int(env.autonomy_interval)}s (set PMM_AUTONOMY_INTERVAL=0 to disable).",
                flush=True,
            )
        else:
            print(
                "[INFO] Autonomy: OFF (set PMM_AUTONOMY_INTERVAL>0 to enable).",
                flush=True,
            )
        if env.reflect_enabled:
            print(
                "[INFO] Reflection: ON — will attempt when cooldown gates are met (set PMM_REFLECT=0 to disable).",
                flush=True,
            )
        else:
            print(
                "[INFO] Reflection: OFF (set PMM_REFLECT=1 to enable).",
                flush=True,
            )
    except Exception:
        # Banner is best-effort; never block REPL
        pass
    try:
        while True:
            user = input("> ").strip()
            if not user:
                continue
            # Metrics toggle commands
            if user.strip() == "--@metrics on":
                metrics_view.on()
                print("[metrics view: ON]", flush=True)
                continue
            if user.strip() == "--@metrics off":
                metrics_view.off()
                print("[metrics view: OFF]", flush=True)
                continue

            if user.lower() in {"exit", "quit", "/q"}:
                print("bye.")
                try:
                    rt.stop_autonomy()
                except Exception:
                    pass
                return
            reply = rt.handle_user(user)
            print(reply, flush=True)
            # One-shot continuity notice after first reply following identity_adopt (strict ordering)
            try:
                events = rt.eventlog.read_all()
                if should_print_identity_notice(events):
                    ident = build_identity(events)
                    nm = ident.get("name")
                    if nm:
                        print(f"[identity] adopted name: {nm}", flush=True)
            except Exception:
                pass
            # When metrics view is enabled, print a concise snapshot after reply
            if metrics_view.enabled:
                try:
                    snap = metrics_view.snapshot(rt.eventlog)
                    print(MetricsView.render(snap), flush=True)
                except Exception:
                    # Never crash REPL for metrics
                    pass
            if env.reflect_enabled:
                try:
                    runtime_maybe_reflect(rt.eventlog, rt.cooldown)
                except Exception:
                    # best-effort reflection, never crash REPL
                    pass
    except (EOFError, KeyboardInterrupt):
        print("\nbye.")
        # Ensure background autonomy loop is stopped
        try:
            rt.stop_autonomy()
        except Exception:
            pass
        sys.exit(0)


if __name__ == "__main__":
    main()
