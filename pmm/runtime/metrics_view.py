from __future__ import annotations

from pmm.config import (
    REFLECTION_SKIPPED,
)
from pmm.runtime.stage_tracker import StageTracker
from pmm.storage.projection import build_identity, build_self_model

_REFLECTION_REASON_LABELS = {
    "due_to_cadence": "waiting for reflection cooldown",
    "due_to_min_time": "waiting for minimum time gap",
    "due_to_min_turns": "waiting for minimum turn gap",
    "due_to_time": "waiting for scheduled window",
    "due_to_low_novelty": "blocked: needs more novelty",
}


def humanize_reflect_reason(reason: str) -> str:
    raw = "" if reason is None else str(reason)
    key = raw.strip().lower()
    human = _REFLECTION_REASON_LABELS.get(key)
    if human:
        return human
    if key:
        return raw.replace("_", " ")
    return "waiting to reflect"


class MetricsView:
    def __init__(self) -> None:
        self.enabled: bool = False

    def on(self) -> None:
        self.enabled = True

    def off(self) -> None:
        self.enabled = False

    def snapshot(self, eventlog, memegraph=None) -> dict:
        events: list[dict] = eventlog.read_tail(limit=1000)
        reflect_skip: str = "none"
        stage: str = "none"
        priority_top5: list[dict] = []
        memegraph_metrics: dict | None = None

        # Use the new hybrid approach: read from DB first, recompute only if needed
        from pmm.runtime.loop import (
            CADENCE_BY_STAGE,
            DRIFT_MULT_BY_STAGE,
            _resolve_reflection_cadence,
        )
        from pmm.runtime.metrics import get_or_compute_ias_gas

        ias, gas = get_or_compute_ias_gas(eventlog)

        # Walk from tail for other fields
        for ev in reversed(events):
            k = ev.get("kind")
            if reflect_skip == "none" and k == REFLECTION_SKIPPED:
                rs = (ev.get("meta") or {}).get("reason")
                if rs:
                    reflect_skip = str(rs)
            if stage == "none" and k == "stage_progress":
                st = (ev.get("meta") or {}).get("stage")
                if st:
                    stage = str(st)
            if not priority_top5 and k == "priority_update":
                r = (ev.get("meta") or {}).get("ranking") or []
                if isinstance(r, list):
                    for item in r:
                        try:
                            cid = str(item.get("cid"))
                            sc = float(item.get("score"))
                            priority_top5.append({"cid": cid, "score": sc})
                        except Exception:
                            continue

        # Open commitments count and top3 (cid+text)
        model = build_self_model(events)
        open_map = model.get("commitments", {}).get("open", {})
        open_count = len(open_map)
        top3 = []
        for cid, meta in list(open_map.items())[:3]:
            top3.append({"cid": cid, "text": str((meta or {}).get("text") or "")})

        if memegraph is not None:
            try:
                metrics = memegraph.last_batch_metrics
                if isinstance(metrics, dict) and metrics:
                    memegraph_metrics = dict(metrics)
            except Exception:
                memegraph_metrics = None

        # Identity snapshot
        ident = build_identity(events)
        name = ident.get("name") or "none"
        traits = ident.get("traits") or {}
        try:
            sorted_traits = sorted(
                traits.items(), key=lambda kv: abs(float(kv[1]) - 0.5), reverse=True
            )
        except Exception:
            sorted_traits = list(traits.items())
        top_traits = [
            {"trait": k[:3].upper(), "v": float(v)} for k, v in sorted_traits[:3]
        ]

        # Stage inference fallback
        try:
            stage_now, _snap = StageTracker.infer_stage(events)
            stage_now = stage_now or "S0"
        except Exception:
            stage_now = "S0"
        if stage == "none":
            stage = stage_now

        # Traits two-decimal vector with safe defaults
        def _two(v: float) -> str:
            try:
                return f"{float(v):.2f}"
            except Exception:
                return "0.00"

        tv = {
            "O": _two(traits.get("openness", 0.0)),
            "C": _two(traits.get("conscientiousness", 0.0)),
            "E": _two(traits.get("extraversion", 0.0)),
            "A": _two(traits.get("agreeableness", 0.0)),
            "N": _two(traits.get("neuroticism", 0.0)),
        }
        line1 = (
            f"identity={name} | stage={stage_now} | "
            f"traits=[O:{tv['O']} C:{tv['C']} E:{tv['E']} A:{tv['A']} N:{tv['N']}]"
        )

        try:
            mt, ms = _resolve_reflection_cadence(events)
            cad = {"min_turns": int(mt), "min_time_s": int(ms)}
        except Exception:
            cad = CADENCE_BY_STAGE.get(stage_now, CADENCE_BY_STAGE.get("S0", {}))
        dmult = DRIFT_MULT_BY_STAGE.get(stage_now, DRIFT_MULT_BY_STAGE.get("S0", {}))

        def _fmt_float(x) -> str:
            try:
                return f"{float(x):g}"
            except Exception:
                return "0"

        line2 = (
            f"reflect[minT={int(cad.get('min_turns', 0))}, minS={int(cad.get('min_time_s', 0))}] "
            f"drift_mult={{O:{_fmt_float(dmult.get('openness', 1.0))}, "
            f"C:{_fmt_float(dmult.get('conscientiousness', 1.0))}, "
            f"N:{_fmt_float(dmult.get('neuroticism', 1.0))}}}"
        )

        return {
            "telemetry": {"IAS": ias, "GAS": gas},
            "reflect_skip": reflect_skip,
            "stage": stage,
            "open_commitments": {"count": open_count, "top3": top3},
            "priority_top5": priority_top5,
            "identity": {"name": name, "top_traits": top_traits, "traits_full": tv},
            "self_model_lines": [line1, line2],
            "memegraph": memegraph_metrics,
        }

    @staticmethod
    def render(snap: dict) -> str:
        tel = snap.get("telemetry", {})
        ias = float(tel.get("IAS", 0.0))
        gas = float(tel.get("GAS", 0.0))
        stage = snap.get("stage", "none")
        rs = snap.get("reflect_skip", "none")
        oc = snap.get("open_commitments", {})
        ocn = int(oc.get("count", 0))
        parts = [f"[METRICS] IAS={ias:.3f} GAS={gas:.3f} | stage={stage} | open={ocn}"]
        if rs != "none":
            parts.insert(0, f"[REFLECTION] {humanize_reflect_reason(rs)}")
        sm_lines = snap.get("self_model_lines") or []
        for ln in sm_lines:
            if isinstance(ln, str) and ln:
                parts.append(ln)
        ident = snap.get("identity", {})
        nm = ident.get("name", "none")
        t3 = ident.get("top_traits", [])
        if nm or t3:
            tparts = [f"{it['trait']}={it['v']:.2f}" for it in t3]
            parts.append(f"[IDENTITY] name={nm} | " + ", ".join(tparts))
        # Always render the full OCEAN vector explicitly for clarity
        tv = ident.get("traits_full", {})
        if tv:
            parts.append(
                f"[TRAITS] O={tv.get('O','0.00')} C={tv.get('C','0.00')} "
                f"E={tv.get('E','0.00')} A={tv.get('A','0.00')} "
                f"N={tv.get('N','0.00')}"
            )
        pr = snap.get("priority_top5", [])
        if pr:
            items = [f"{e['cid'][:4]}… {e['score']:.2f}" for e in pr]
            parts.append("[PRIORITY] " + " | ".join(items))

        graph = snap.get("memegraph")
        if isinstance(graph, dict) and graph:

            def _fmt_metric(key: str) -> str:
                try:
                    val = graph.get(key)
                    if isinstance(val, float):
                        return f"{val:.3f}" if key == "duration_ms" else f"{val:.0f}"
                    if isinstance(val, (int, str)):
                        return str(val)
                except Exception:
                    pass
                return "?"

            graph_line = (
                "[MEMEGRAPH] "
                f"nodes={_fmt_metric('nodes')} "
                f"edges={_fmt_metric('edges')} "
                f"batch={_fmt_metric('batch_events')} "
                f"ms={_fmt_metric('duration_ms')} "
                f"rss_kb={_fmt_metric('rss_kb')}"
            )
            parts.append(graph_line)
        return "\n".join(parts)
