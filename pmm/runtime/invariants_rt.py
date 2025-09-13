from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Dict, Any, Optional
import time

# ---- Gate constants (no env flags) ----
MAX_SCAN_EVENTS = 500  # bounded lookback to keep cost stable


@dataclass(frozen=True)
class Violation:
    code: str  # e.g., "HASH_CHAIN", "CANDIDATE_BEFORE_CLOSE", "TTL_OPEN_COMMITMENTS", "PROJECTION_EQUIV"
    message: str
    details: Dict[str, Any]


def _kind(ev: dict) -> str:
    return ev.get("kind") or ev.get("type") or ""


def _payload(ev: dict) -> dict:
    return ev.get("payload") or {}


def _meta(ev: dict) -> dict:
    return _payload(ev).get("meta") or ev.get("meta") or {}


def _ts(ev: dict) -> float:
    ts = ev.get("ts") or ev.get("timestamp")
    try:
        return float(ts)
    except Exception:
        return 0.0


# ---- Checks ----


def check_hash_chain(evlog) -> List[Violation]:
    if hasattr(evlog, "verify_chain"):
        ok = bool(evlog.verify_chain())
        if not ok:
            return [Violation("HASH_CHAIN", "Hash chain verification failed", {})]
    return []


def check_candidate_before_close(events: Iterable[dict]) -> List[Violation]:
    seen_candidate_for: set[str] = set()
    out: List[Violation] = []
    for ev in events:
        k = _kind(ev)
        pay, meta = _payload(ev), _meta(ev)
        cid = pay.get("commitment_id") or meta.get("commitment_id") or meta.get("cid")
        if not cid:
            continue
        cid = str(cid)
        if k == "evidence_candidate":
            seen_candidate_for.add(cid)
        elif k == "commitment_close":
            if cid not in seen_candidate_for:
                out.append(
                    Violation(
                        "CANDIDATE_BEFORE_CLOSE",
                        "commitment_close without prior evidence_candidate",
                        {"commitment_id": cid},
                    )
                )
    return out


def check_ttl_open_commitments(
    events: Iterable[dict], now_ts: Optional[float] = None
) -> List[Violation]:
    now = float(now_ts if now_ts is not None else time.time())
    opens: Dict[str, Dict[str, Any]] = {}
    closed: set[str] = set()
    out: List[Violation] = []

    for ev in events:
        k = _kind(ev)
        pay, meta = _payload(ev), _meta(ev)
        cid = pay.get("commitment_id") or meta.get("commitment_id") or meta.get("cid")
        if not cid:
            continue
        cid = str(cid)
        if k == "commitment_open":
            opens[cid] = {
                "ts": _ts(ev),
                "ttl": pay.get("ttl_seconds") or meta.get("ttl_seconds"),
                "expire_at": pay.get("expire_at") or meta.get("expire_at"),
            }
        elif k == "commitment_close":
            closed.add(cid)

    for cid, info in opens.items():
        if cid in closed:
            continue
        exp_at = info.get("expire_at")
        ttl = info.get("ttl")
        if exp_at is not None:
            try:
                if now > float(exp_at):
                    out.append(
                        Violation(
                            "TTL_OPEN_COMMITMENTS",
                            "open past expire_at",
                            {"commitment_id": cid},
                        )
                    )
            except Exception:
                # ignore malformed values
                pass
        elif ttl is not None:
            try:
                if now - float(info["ts"]) > float(ttl):
                    out.append(
                        Violation(
                            "TTL_OPEN_COMMITMENTS",
                            "open past ttl_seconds",
                            {"commitment_id": cid},
                        )
                    )
            except Exception:
                pass
    return out


# Optional light determinism probe using your existing directives view (cheap)


def check_projection_equiv(build_directives, events: Iterable[dict]) -> List[Violation]:
    e1 = list(events)
    v1 = build_directives(e1)
    v2 = build_directives(list(e1))
    if v1 != v2:
        return [
            Violation(
                "PROJECTION_EQUIV", "Directives view is not replay-deterministic", {}
            )
        ]
    return []


# ---- Orchestrator ----


def run_invariants_tick(*, evlog, build_directives) -> List[Dict[str, Any]]:
    """
    Read a bounded tail of events, run checks, and return a list of
    'invariant_violation' events to append. Non-blocking; no raises.
    """
    try:
        if hasattr(evlog, "read_tail"):
            try:
                tail = list(evlog.read_tail(limit=MAX_SCAN_EVENTS))
            except TypeError:
                tail = list(evlog.read_tail(MAX_SCAN_EVENTS))
        else:
            all_events = list(evlog.read_all())
            tail = (
                all_events[-MAX_SCAN_EVENTS:]
                if len(all_events) > MAX_SCAN_EVENTS
                else all_events
            )
        violations: List[Violation] = []
        violations += check_hash_chain(evlog)
        violations += check_candidate_before_close(tail)
        violations += check_ttl_open_commitments(tail)
        violations += check_projection_equiv(build_directives, tail)

        out_events: List[Dict[str, Any]] = []
        for v in violations:
            out_events.append(
                {
                    "kind": "invariant_violation",
                    "payload": {
                        "code": v.code,
                        "message": v.message,
                        "details": v.details,
                    },
                }
            )
        return out_events
    except Exception as e:
        # Last resort: surface as a single violation event; never throw
        return [
            {
                "kind": "invariant_violation",
                "payload": {
                    "code": "INVARIANT_CHECK_ERROR",
                    "message": str(e),
                    "details": {},
                },
            }
        ]
