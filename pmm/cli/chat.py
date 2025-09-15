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
from pmm.storage.projection import build_identity, build_self_model
from pmm.runtime.prioritizer import rank_commitments


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
            # Print deterministic header (identity + top commitments + recent trait drift)
            try:

                def _c(s: str, code: str) -> str:
                    try:
                        if os.getenv("PMM_COLOR", "1").lower() in {"0", "false"}:
                            return s
                    except Exception:
                        pass
                    return f"\033[{code}m{s}\033[0m"

                evs_all = rt.eventlog.read_all()
                ident0 = build_identity(evs_all)
                name0 = str(ident0.get("name") or "").strip()
                header_lines: list[str] = []
                if name0:
                    header_lines.append(
                        _c(f"You are {name0}. Speak in first person.", "96")
                    )
                try:
                    model0 = build_self_model(evs_all)
                    open_map = (model0.get("commitments") or {}).get("open") or {}
                    ranking = rank_commitments(evs_all)
                    top_cids = [cid for cid, _ in ranking[:2] if cid in open_map]
                    top_texts: list[str] = []

                    def _short_commit_text(txt: str, limit: int = 80) -> str:
                        import re

                        t = str(txt or "")
                        t = re.sub(r"[`*_#>]+", " ", t)
                        t = re.sub(
                            r"^\s*(?:[-*•]+|\(?[A-Za-z]\)|\(?\d+\)|\d+\.)\s*", "", t
                        )
                        t = re.sub(r"\s+", " ", t).strip()
                        parts = re.split(r"(?<=[\.!?])\s+", t, maxsplit=1)
                        s = (parts[0] or t).strip()
                        if len(s) <= limit:
                            return s
                        cut = s[: limit - 1]
                        if " " in cut:
                            cut = cut.rsplit(" ", 1)[0]
                        return cut.rstrip() + "…"

                    for cid in top_cids:
                        txt = str((open_map.get(cid) or {}).get("text") or "").strip()
                        if not txt:
                            continue
                        line = _short_commit_text(txt, limit=80)
                        if line:
                            top_texts.append(line)
                    if top_texts:
                        header_lines.append(_c("Open commitments:", "33"))
                        for t in top_texts:
                            header_lines.append(f"- {t}")
                    # Projects: show most populous open project deterministically (includes assignments)
                    try:
                        assign: dict[str, str] = {}
                        for e in reversed(evs_all):
                            if e.get("kind") != "project_assign":
                                continue
                            m = e.get("meta") or {}
                            cc = str(m.get("cid") or "")
                            pid = str(m.get("project_id") or "")
                            if cc and cc in open_map and cc not in assign and pid:
                                assign[cc] = pid
                        proj_counts: dict[str, int] = {}
                        for _cid, meta_c in open_map.items():
                            pid0 = (meta_c or {}).get("project_id") or assign.get(_cid)
                            if isinstance(pid0, str) and pid0:
                                proj_counts[pid0] = proj_counts.get(pid0, 0) + 1
                        if proj_counts:
                            max_n = max(proj_counts.values())
                            cands = sorted(
                                [p for p, n in proj_counts.items() if n == max_n]
                            )
                            top_proj = cands[0]
                            header_lines.append(
                                _c(
                                    f"[PROJECT] {top_proj} — {proj_counts[top_proj]} open",
                                    "35",
                                )
                            )
                    except Exception:
                        pass
                    # Recent trait drift sign-only (+O -C) from most recent trait_update
                    try:
                        last_trait = None
                        for e in reversed(evs_all):
                            if e.get("kind") == "trait_update":
                                last_trait = e
                                break
                        if last_trait:
                            m = last_trait.get("meta") or {}
                            abbr = {
                                "openness": "O",
                                "conscientiousness": "C",
                                "extraversion": "E",
                                "agreeableness": "A",
                                "neuroticism": "N",
                                "o": "O",
                                "c": "C",
                                "e": "E",
                                "a": "A",
                                "n": "N",
                            }
                            tokens: list[str] = []
                            d = m.get("delta")
                            if isinstance(d, dict):
                                for k, v in d.items():
                                    key = abbr.get(str(k).lower())
                                    if not key:
                                        continue
                                    try:
                                        dv = float(v)
                                    except Exception:
                                        continue
                                    if dv > 0:
                                        tokens.append(f"+{key}")
                                    elif dv < 0:
                                        tokens.append(f"-{key}")
                                    if len(tokens) >= 3:
                                        break
                            else:
                                key = abbr.get(str(m.get("trait") or "").lower())
                                try:
                                    dv = (
                                        float(m.get("delta"))
                                        if m.get("delta") is not None
                                        else 0.0
                                    )
                                except Exception:
                                    dv = 0.0
                                if key and dv:
                                    tokens.append(("+" if dv > 0 else "-") + key)
                            if tokens:
                                header_lines.append(
                                    _c("Recent trait drift: " + " ".join(tokens), "36")
                                )
                    except Exception:
                        pass
                except Exception:
                    pass
                if header_lines:
                    print("\n".join(header_lines), flush=True)
            except Exception:
                pass
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
                        msg = f"[stage] {prev_stage_label or '—'} → {stage_label} (cadence updated)"
                        try:
                            msg = _c(msg, "34")
                        except Exception:
                            pass
                        print(msg, flush=True)
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
                        msg2 = (
                            f"[policy] cooldown.novelty_threshold → {cooldown_thr:.2f}"
                        )
                        try:
                            msg2 = _c(msg2, "33")
                        except Exception:
                            pass
                        print(msg2, flush=True)
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
            # Identity lifecycle breadcrumbs: proposal and adoption (new)
            try:
                evs_i = rt.eventlog.read_all()
                # Track last printed ids
                if not hasattr(main, "_last_identity_prop_id"):
                    setattr(main, "_last_identity_prop_id", None)
                if not hasattr(main, "_last_identity_adopt_id"):
                    setattr(main, "_last_identity_adopt_id", None)
                last_prop_printed = getattr(main, "_last_identity_prop_id")
                last_adopt_printed = getattr(main, "_last_identity_adopt_id")
                # Print most recent proposal once
                for e in reversed(evs_i):
                    if e.get("kind") == "identity_propose":
                        eid = int(e.get("id") or 0)
                        if eid and eid != last_prop_printed:
                            tno = (e.get("meta") or {}).get("tick")
                            msg = f"[IDENTITY] proposed: {e.get('content') or ''} (tick {tno})"
                            try:
                                msg = _c(msg, "36")
                            except Exception:
                                pass
                            print(msg, flush=True)
                            setattr(main, "_last_identity_prop_id", eid)
                        break
                # Print most recent adoption once (already a one-shot banner after first reply too)
                for e in reversed(evs_i):
                    if e.get("kind") == "identity_adopt":
                        eid = int(e.get("id") or 0)
                        if eid and eid != last_adopt_printed:
                            tno = (e.get("meta") or {}).get("tick")
                            nm = (e.get("meta") or {}).get("name") or (
                                e.get("content") or ""
                            )
                            msg = f"[IDENTITY] adopted: {nm} (tick {tno})"
                            try:
                                msg = _c(msg, "36")
                            except Exception:
                                pass
                            print(msg, flush=True)
                            setattr(main, "_last_identity_adopt_id", eid)
                        break
            except Exception:
                pass
            # Bridge observability: print CurriculumUpdate→PolicyUpdate linkage (src_id)
            try:
                evs_b = rt.eventlog.read_all()
                if not hasattr(main, "_last_bridge_policy_id"):
                    setattr(main, "_last_bridge_policy_id", None)
                last_bridge_printed = getattr(main, "_last_bridge_policy_id")
                for e in reversed(evs_b):
                    if e.get("kind") != "policy_update":
                        continue
                    m = e.get("meta") or {}
                    src = m.get("src_id")
                    if src is None:
                        continue
                    eid = int(e.get("id") or 0)
                    if eid and eid != last_bridge_printed:
                        msg = f"[BRIDGE] CurriculumUpdate→PolicyUpdate (pu_id={eid}, src_id={src})"
                        try:
                            msg = _c(msg, "35")
                        except Exception:
                            pass
                        print(msg, flush=True)
                        setattr(main, "_last_bridge_policy_id", eid)
                    break
            except Exception:
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
                            try:
                                msg = _c(f"[reminder] Commitment #{cid} is due!", "31")
                            except Exception:
                                msg = f"[reminder] Commitment #{cid} is due!"
                            print(msg, flush=True)
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
                        msg = f"[IDENTITY] adopted name: {nm}"
                        try:
                            msg = _c(msg, "36")
                        except Exception:
                            pass
                        print(msg, flush=True)
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
