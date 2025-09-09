from __future__ import annotations

from typing import Dict, List, Optional

from pmm.storage.projection import build_self_model, build_identity


class MetricsView:
    def __init__(self) -> None:
        self.enabled: bool = False

    def on(self) -> None:
        self.enabled = True

    def off(self) -> None:
        self.enabled = False

    def snapshot(self, eventlog) -> Dict:
        events: List[Dict] = eventlog.read_all()
        latest_ias: Optional[float] = None
        latest_gas: Optional[float] = None
        reflect_skip: str = "none"
        stage: str = "none"
        priority_top5: List[Dict] = []

        # Walk from tail for most recent items
        for ev in reversed(events):
            k = ev.get("kind")
            if latest_ias is None and k == "autonomy_tick":
                tel = (ev.get("meta") or {}).get("telemetry") or {}
                if "IAS" in tel and "GAS" in tel:
                    latest_ias = float(tel["IAS"])
                    latest_gas = float(tel["GAS"])
            if reflect_skip == "none" and k == "debug":
                rs = (ev.get("meta") or {}).get("reflect_skip")
                if rs:
                    reflect_skip = str(rs)
            if stage == "none" and k == "stage_update":
                st = (ev.get("meta") or {}).get("to")
                if st:
                    stage = str(st)
            if not priority_top5 and k == "priority_update":
                r = (ev.get("meta") or {}).get("ranking") or []
                # Normalize items {cid, score}
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

        # Identity snapshot
        ident = build_identity(events)
        name = ident.get("name") or "none"
        traits = ident.get("traits") or {}
        # Pick top 3 by absolute deviation from 0.5 for display
        try:
            sorted_traits = sorted(
                traits.items(), key=lambda kv: abs(float(kv[1]) - 0.5), reverse=True
            )
        except Exception:
            sorted_traits = list(traits.items())
        top_traits = [
            {"trait": k[:3].upper(), "v": float(v)} for k, v in sorted_traits[:3]
        ]

        # Defaults if no telemetry yet
        if latest_ias is None:
            latest_ias, latest_gas = 0.0, 0.0

        return {
            "telemetry": {"IAS": latest_ias, "GAS": latest_gas},
            "reflect_skip": reflect_skip,
            "stage": stage,
            "open_commitments": {"count": open_count, "top3": top3},
            "priority_top5": priority_top5,
            "identity": {"name": name, "top_traits": top_traits},
        }

    @staticmethod
    def render(snap: Dict) -> str:
        tel = snap.get("telemetry", {})
        ias = float(tel.get("IAS", 0.0))
        gas = float(tel.get("GAS", 0.0))
        stage = snap.get("stage", "none")
        rs = snap.get("reflect_skip", "none")
        oc = snap.get("open_commitments", {})
        ocn = int(oc.get("count", 0))
        parts = [
            f"[METRICS] IAS={ias:.2f} GAS={gas:.2f} | stage={stage} | open={ocn} | reflect_skip={rs}"
        ]
        ident = snap.get("identity", {})
        nm = ident.get("name", "none")
        t3 = ident.get("top_traits", [])
        if nm or t3:
            tparts = [f"{it['trait']}={it['v']:.2f}" for it in t3]
            parts.append(f"[IDENTITY] name={nm} | " + ", ".join(tparts))
        pr = snap.get("priority_top5", [])
        if pr:
            items = [f"{e['cid'][:4]}… {e['score']:.2f}" for e in pr]
            parts.append("[PRIORITY] " + " | ".join(items))
        return "\n".join(parts)
