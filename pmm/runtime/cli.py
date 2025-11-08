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
from pmm.core.meme_graph import MemeGraph
import json as _json


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
    print("\n🧠  Persistent Mind Model")
    print("────────────────────────────")
    print("Select a model to chat with:\n")

    models = _gather_models()

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
    print("  /graph stats            Show event graph stats")
    print("  /graph thread <CID>     Show thread for a commitment")
    print("  /config retrieval fixed limit <N>  Set fixed window limit (idempotent)")
    print("  /rebuild-fast           Verify fast RSM rebuild matches full")
    print("  /pm        Admin commands (type '/pm' for help)")
    print("  /raw      Show last assistant message with markers")
    print("  /model    Switch to a different model")
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
    selected, use_openai, model_name = _resolve_model_selection(choice_raw, models)

    print(f"\n→ Using model: {selected}\n")
    print("Type '/exit' to quit.\n")

    elog = EventLog(db_path)
    adapter = _instantiate_adapter(use_openai, model_name)
    loop = RuntimeLoop(eventlog=elog, adapter=adapter, replay=False)

    try:
        while True:
            user = input("You> ")
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
            if cmd.startswith("/rsm"):
                output = handle_rsm_command(raw_cmd, elog)
                if output:
                    print(output)
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
            if cmd in {"/raw"}:
                # Show last assistant message exactly as logged (including markers)
                tail = [
                    e
                    for e in elog.read_tail(200)
                    if e.get("kind") == "assistant_message"
                ]
                if tail:
                    print(f"Assistant (raw)> {tail[-1].get('content') or ''}")
                else:
                    print("No assistant messages yet.")
                continue
            if cmd.startswith("/model"):
                out = handle_model_command(raw_cmd, loop)
                if out:
                    print(out)
                continue
            events = loop.run_turn(user)
            ai_msgs = [e for e in events if e.get("kind") == "assistant_message"]
            if ai_msgs:
                content = ai_msgs[-1].get("content") or ""
                # Hide marker lines for conversational display
                _hidden = ("COMMIT:", "CLOSE:", "CLAIM:", "REFLECT:")
                visible_lines = [
                    ln for ln in content.splitlines() if not ln.startswith(_hidden)
                ]
                assistant_output = "\n".join(visible_lines).strip()
                if assistant_output:
                    print(f"Assistant> {assistant_output}")
                # Optional badge: per-turn counts (derived deterministically from ledger)
                # Count claims from this assistant message
                claims = sum(
                    1 for ln in content.splitlines() if ln.startswith("CLAIM:")
                )
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
                    print(f"({opened} opened, {closed} closed, {claims} claims)")
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


def handle_pm_command(command: str, eventlog: EventLog) -> Optional[str]:
    parts = command.strip().split()
    if not parts or parts[0].lower() != "/pm":
        return None
    # Help root
    if len(parts) == 1 or parts[1].lower() in {"help", "?"}:
        return (
            "Admin topics: graph | retrieval | checkpoint | rebuild | config\n"
            "Examples:\n"
            "  /pm graph stats\n  /pm graph thread <CID>\n"
            "  /pm retrieval config fixed limit 7\n  /pm retrieval last\n"
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
                content=_json.dumps(cfg, separators=(",", ":")),
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
                data = _json.loads(ev.get("content") or "{}")
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
                content=_json.dumps(desired, separators=(",", ":")),
                meta={"source": "cli"},
            )
            return "Autonomy thresholds updated"
        return "Usage: /pm config autonomy key=value …"
    return "Unknown /pm topic. Try '/pm' for help."


def _last_autonomy_cfg(eventlog: EventLog) -> Optional[Dict]:
    cfg = None
    for ev in eventlog.read_all():
        if ev.get("kind") != "config":
            continue
        try:
            data = _json.loads(ev.get("content") or "{}")
        except Exception:
            continue
        if isinstance(data, dict) and data.get("type") == "autonomy_thresholds":
            cfg = data
    return cfg


def _policy_forbids(eventlog: EventLog, *, source: str, kind: str) -> bool:
    import json as _j

    policy = None
    for ev in eventlog.read_all()[::-1]:
        if ev.get("kind") != "config":
            continue
        try:
            data = _j.loads(ev.get("content") or "{}")
        except Exception:
            continue
        if isinstance(data, dict) and data.get("type") == "policy":
            policy = data
            break
    if not policy:
        return False
    fs = policy.get("forbid_sources") or {}
    kinds = fs.get(source)
    return isinstance(kinds, list) and kind in kinds


def _message_events(events):
    return [e for e in events if e.get("kind") in ("user_message", "assistant_message")]


def _embedding_map(events, *, model: str, dims: int):
    out = {}
    for e in events:
        if e.get("kind") != "embedding_add":
            continue
        try:
            data = _json.loads(e.get("content") or "{}")
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
    events = eventlog.read_all()
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
    events = eventlog.read_all()
    msgs = _message_events(events)
    embs = _embedding_map(events, model=model, dims=dims)
    return f"messages:{len(msgs)} embeddings:{len(embs)} model:{model} dims:{dims}"


def _handle_retrieval_verify(eventlog: EventLog, turn_id: int) -> str:
    # Find the retrieval_selection for this turn
    target = None
    for e in reversed(eventlog.read_all()):
        if e.get("kind") == "retrieval_selection":
            try:
                data = _json.loads(e.get("content") or "{}")
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
    # Find the last user_message before turn_id
    events = eventlog.read_all()
    query_text = ""
    for e in reversed(events):
        if int(e.get("id", 0)) >= int(turn_id):
            continue
        if e.get("kind") == "user_message":
            query_text = e.get("content") or ""
            break
    if not query_text:
        return "Unable to locate query text"
    # Build index and recompute scores
    from pmm.retrieval.vector import (
        DeterministicEmbedder,
        cosine,
        build_index,
        candidate_messages,
    )

    idx = build_index(events, model=model, dims=dims)
    qv = DeterministicEmbedder(model=model, dims=dims).embed(query_text)
    cands = candidate_messages(events, up_to_id=turn_id)
    scored = []
    for ev in cands:
        eid = int(ev.get("id", 0))
        vec = idx.get(eid)
        if vec is None:
            vec = DeterministicEmbedder(model=model, dims=dims).embed(
                ev.get("content") or ""
            )
        s = cosine(qv, vec)
        scored.append((eid, s))
    scored.sort(key=lambda t: (-t[1], t[0]))
    limit = len(selected)
    top_ids = [eid for (eid, _s) in scored[:limit]]
    return (
        "OK" if top_ids == selected else f"Mismatch: expected {selected} got {top_ids}"
    )


def _handle_checkpoint(eventlog: EventLog) -> str:
    events = eventlog.read_all()
    if not events:
        return "No events to checkpoint."
    # Find last summary_update to anchor manifest
    last_summary = None
    for ev in reversed(events):
        if ev.get("kind") == "summary_update":
            last_summary = ev
            break
    if not last_summary:
        return "No summary_update found to anchor checkpoint."
    up_to = int(last_summary.get("id", 0))
    # Compute root hash over hash sequence up to anchor
    hashes = [e.get("hash") or "" for e in events if int(e.get("id", 0)) <= up_to]
    root_blob = _json.dumps(hashes, separators=(",", ":"))
    import hashlib as _hl

    digest = _hl.sha256(root_blob.encode("utf-8")).hexdigest()
    # Idempotent: check last manifest
    last_manifest = None
    for ev in reversed(events):
        if ev.get("kind") == "checkpoint_manifest":
            last_manifest = ev
            break
    if last_manifest:
        try:
            data = _json.loads(last_manifest.get("content") or "{}")
        except Exception:
            data = {}
        if int(data.get("up_to_id", 0)) == up_to and data.get("root_hash") == digest:
            return "No change (idempotent)"
    content = _json.dumps(
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
    mg = MemeGraph(eventlog)
    mg.rebuild(eventlog.read_all())
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
    return "Usage: /graph stats | /graph thread <CID>"


def _last_retrieval_config(eventlog: EventLog) -> Optional[Dict]:
    cfg = None
    for ev in eventlog.read_all():
        if ev.get("kind") != "config":
            continue
        try:
            data = _json.loads(ev.get("content") or "{}")
        except Exception:
            continue
        if isinstance(data, dict) and data.get("type") == "retrieval":
            cfg = data
    return cfg


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
        kind="config", content=_json.dumps(desired, separators=(",", ":")), meta={}
    )
    return f"Retrieval config updated: limit={limit}"


def handle_rebuild_fast(eventlog: EventLog) -> Optional[str]:
    from pmm.core.ledger_mirror import LedgerMirror

    lm_full = LedgerMirror(eventlog, listen=False)
    snap_full = lm_full.rsm_snapshot()

    # Simulate fast rebuild by constructing a fresh mirror and calling private fast path
    # (exposed here as a CLI diagnostic only).
    lm_fast = LedgerMirror(eventlog, listen=False)
    try:
        # Monkey: call internal method if present
        if hasattr(lm_fast, "rebuild_fast"):
            getattr(lm_fast, "rebuild_fast")()
        snap_fast = lm_fast.rsm_snapshot()
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
