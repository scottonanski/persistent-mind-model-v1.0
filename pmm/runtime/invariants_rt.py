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


def check_identity_propose_before_adopt(events: Iterable[dict]) -> List[Violation]:
    """Check that every identity_adopt has a preceding identity_propose."""
    adopts = []
    proposes = []

    for ev in events:
        k = _kind(ev)
        if k == "identity_adopt":
            # Ignore bootstrap identity adoption emitted by AutonomyLoop on fresh logs
            meta = _meta(ev)
            if (
                meta.get("bootstrap") is True
                or str(meta.get("reason") or "").strip() == "default_bootstrap"
            ):
                continue
            adopts.append(ev)
        elif k == "identity_propose":
            proposes.append(ev)

    violations = []
    for adopt in adopts:
        adopt_id = adopt.get("id", 0)
        has_proposal = False

        # Check if there's a proposal before this adoption
        for propose in proposes:
            propose_id = propose.get("id", 0)
            if propose_id < adopt_id:
                has_proposal = True
                break

        if not has_proposal:
            violations.append(
                Violation(
                    "IDENTITY_ADOPT_WITHOUT_PROPOSE",
                    "identity_adopt without prior identity_propose",
                    {"adopt_event_id": adopt_id},
                )
            )

    return violations


def check_trait_drift_bounds(events: Iterable[dict]) -> List[Violation]:
    """Check that trait updates are within [-0.05, +0.05]."""
    violations = []

    for ev in events:
        k = _kind(ev)
        if k == "trait_update":
            meta = _meta(ev)
            changes = meta.get("changes", {})

            for trait, delta in changes.items():
                try:
                    delta_value = float(delta)
                    if delta_value < -0.05 or delta_value > 0.05:
                        violations.append(
                            Violation(
                                "TRAIT_DRIFT_OUT_OF_BOUNDS",
                                f"Trait {trait} drift {delta_value} outside bounds [-0.05, +0.05]",
                                {"trait": trait, "delta": delta_value},
                            )
                        )
                except (ValueError, TypeError):
                    # Skip malformed delta values
                    continue

    return violations


def check_min_turns_between_identity_adopts(events: Iterable[dict]) -> List[Violation]:
    """Check that there are no two identity adoptions within < min_turns."""
    from pmm.runtime.loop import MIN_TURNS_BETWEEN_IDENTITY_ADOPTS

    adopts = []
    for ev in events:
        k = _kind(ev)
        if k == "identity_adopt":
            adopts.append(ev)

    violations = []
    # Check consecutive adoptions
    for i in range(len(adopts) - 1):
        current_adopt = adopts[i]
        next_adopt = adopts[i + 1]

        # Count autonomy_tick events between these two adoptions
        ticks_between = 0
        counting = False
        for ev in events:
            k = _kind(ev)
            if not counting:
                if ev.get("id") == current_adopt.get("id"):
                    counting = True
            else:
                if ev.get("id") == next_adopt.get("id"):
                    break
                if k == "autonomy_tick":
                    ticks_between += 1

        if ticks_between < MIN_TURNS_BETWEEN_IDENTITY_ADOPTS:
            violations.append(
                Violation(
                    "IDENTITY_ADOPT_TOO_FREQUENT",
                    f"Identity adoptions too close: {ticks_between} ticks < {MIN_TURNS_BETWEEN_IDENTITY_ADOPTS}",
                    {
                        "current_adopt_id": current_adopt.get("id"),
                        "next_adopt_id": next_adopt.get("id"),
                        "ticks_between": ticks_between,
                    },
                )
            )

    return violations


def check_commitments_rebound_after_identity_adopt(
    events: Iterable[dict],
) -> List[Violation]:
    """Check that commitments referencing old identity are closed or rebound after identity adoption."""
    adopts = []
    commitments = []

    for ev in events:
        k = _kind(ev)
        if k == "identity_adopt":
            adopts.append(ev)
        elif k == "commitment_open":
            commitments.append(ev)

    violations = []
    # For each adoption, check if there are commitments with the old name
    # that weren't properly closed or rebound
    for adopt in adopts:
        meta = _meta(adopt)
        new_name = meta.get("name")
        adopt_id = adopt.get("id", 0)

        if not new_name:
            continue

        # Find commitments that were open before this adoption
        for commit in commitments:
            commit_id = commit.get("id", 0)
            # Only check commitments opened before this adoption
            if commit_id < adopt_id:
                commit_meta = _meta(commit)
                commit_text = commit.get("content", "") or commit_meta.get("text", "")

                # If commitment text contains the new identity name, it should be handled
                if new_name.lower() in commit_text.lower():
                    # Check if there's a commitment_rebind or commitment_close event for this commitment
                    handled = False
                    for ev in events:
                        ev_id = ev.get("id", 0)
                        ev_kind = _kind(ev)

                        # Only check events after the adoption
                        if ev_id <= adopt_id:
                            continue

                        ev_meta = _meta(ev)
                        ev_cid = ev_meta.get("cid")
                        commit_cid = commit_meta.get("cid")

                        if ev_cid == commit_cid and ev_kind in [
                            "commitment_rebind",
                            "commitment_close",
                        ]:
                            handled = True
                            break

                    if not handled:
                        violations.append(
                            Violation(
                                "COMMITMENT_NOT_REBOUND",
                                "Commitment with old identity name not closed or rebound after adoption",
                                {
                                    "commitment_id": commit_meta.get("cid"),
                                    "commitment_text": commit_text,
                                    "identity_adopt_id": adopt_id,
                                },
                            )
                        )

    return violations


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
        violations += check_identity_propose_before_adopt(tail)
        violations += check_trait_drift_bounds(tail)
        violations += check_min_turns_between_identity_adopts(tail)
        violations += check_commitments_rebound_after_identity_adopt(tail)

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
