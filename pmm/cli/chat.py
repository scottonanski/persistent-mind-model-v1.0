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
            # Optional stage/policy notices for UX clarity
            try:
                if os.getenv("PMM_CLI_STAGE_NOTICE", "0").lower() in {"1", "true"}:
                    evs = rt.eventlog.read_all()
                    # Track last printed stage and cooldown threshold in function locals via nonlocal closure pattern
                    if not hasattr(main, "_last_stage_label"):
                        setattr(main, "_last_stage_label", None)
                    if not hasattr(main, "_last_cooldown_thr"):
                        setattr(main, "_last_cooldown_thr", None)

                    # Resolve most recent stage label from stage_update or policy_update(component="reflection")
                    stage_label = None
                    for e in reversed(evs):
                        if e.get("kind") == "stage_update":
                            stage_label = (e.get("meta") or {}).get("to")
                            break
                        if e.get("kind") == "policy_update":
                            m = e.get("meta") or {}
                            if str(m.get("component")) == "reflection":
                                stage_label = m.get("stage") or stage_label
                                if stage_label:
                                    break
                    prev_stage_label = getattr(main, "_last_stage_label")
                    if stage_label and stage_label != prev_stage_label:
                        print(
                            f"[stage] {prev_stage_label or '—'} → {stage_label} (cadence updated)",
                            flush=True,
                        )
                        setattr(main, "_last_stage_label", stage_label)

                    # Resolve most recent cooldown novelty threshold from policy_update(component="cooldown")
                    cooldown_thr = None
                    for e in reversed(evs):
                        if e.get("kind") != "policy_update":
                            continue
                        m = e.get("meta") or {}
                        if str(m.get("component")) != "cooldown":
                            continue
                        params = m.get("params") or {}
                        if "novelty_threshold" in params:
                            try:
                                cooldown_thr = float(params.get("novelty_threshold"))
                            except Exception:
                                cooldown_thr = None
                            break
                    prev_thr = getattr(main, "_last_cooldown_thr")
                    if cooldown_thr is not None and cooldown_thr != prev_thr:
                        print(
                            f"[policy] cooldown.novelty_threshold → {cooldown_thr:.2f}",
                            flush=True,
                        )
                        setattr(main, "_last_cooldown_thr", cooldown_thr)
            except Exception:
                # Never crash REPL on notices
                pass
            # Optional: print when a reflection-driven commitment opens
            try:
                evs = rt.eventlog.read_all()
                last_ev = evs[-1] if evs else None
                if last_ev and last_ev.get("kind") == "commitment_open":
                    meta = last_ev.get("meta") or {}
                    if meta.get("reason") == "reflection":
                        # Track last seen to avoid duplicates
                        if not hasattr(main, "_last_commitment_id"):
                            setattr(main, "_last_commitment_id", None)
                        prev_cid = getattr(main, "_last_commitment_id")
                        if last_ev.get("id") != prev_cid:
                            print("[commitment] opened from reflection", flush=True)
                            setattr(main, "_last_commitment_id", last_ev.get("id"))
            except Exception:
                # Never crash REPL on notice
                pass
            # Optional reminder notices for commitments due
            try:
                if os.getenv("PMM_CLI_REMINDER_NOTICE", "0").lower() in {"1", "true"}:
                    evs2 = rt.eventlog.read_all()
                    if not hasattr(main, "_printed_reminder_ids"):
                        setattr(main, "_printed_reminder_ids", set())
                    printed = getattr(main, "_printed_reminder_ids")
                    # Print any new commitment_reminder since last check
                    for e in evs2:
                        if e.get("kind") != "commitment_reminder":
                            continue
                        eid = int(e.get("id") or 0)
                        if eid in printed:
                            continue
                        cid = (e.get("meta") or {}).get("cid")
                        if cid:
                            print(f"[reminder] Commitment #{cid} is due!", flush=True)
                            printed.add(eid)
            except Exception:
                pass
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
