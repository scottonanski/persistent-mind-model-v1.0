"""Self-assessment and meta-reflection logic for the runtime loop.

Extracted from the monolithic loop.py to improve maintainability.
"""

from __future__ import annotations

import hashlib as _hashlib
import json as _json
from typing import TYPE_CHECKING

from pmm.runtime.loop import io as _io
from pmm.runtime.stage_tracker import StageTracker

if TYPE_CHECKING:
    from pmm.storage.eventlog import EventLog


def _sha256_json(obj) -> str:
    """Compute SHA256 hash of JSON-serialized object."""
    try:
        data = _json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return _hashlib.sha256(data).hexdigest()
    except Exception:
        return ""


def maybe_emit_meta_reflection(eventlog: EventLog, *, window: int = 5) -> int | None:
    """Emit a meta_reflection every `window` reflections, idempotently.

        Computes simple window metrics: opened, closed, trait_delta_abs, action_count, and an efficiency score.
        Returns new event id or None if not emitted.
    {{ ... }}

        Extracted from loop.py - preserves exact behavior.
    """
    try:
        events = eventlog.read_all()
        refl_ids = [
            int(e.get("id") or 0) for e in events if e.get("kind") == "reflection"
        ]
        if len(refl_ids) < int(window):
            return None
        expected = len(refl_ids) // int(window)
        actual = sum(1 for e in events if e.get("kind") == "meta_reflection")
        if actual >= expected:
            return None
        start_id = refl_ids[-int(window)]
        end_id = refl_ids[-1]
        opened = 0
        closed = 0
        action_cnt = 0
        trait_abs = 0.0
        for ev in events:
            try:
                eid = int(ev.get("id") or 0)
            except Exception:
                continue
            if eid <= start_id or eid > end_id:
                continue
            k = ev.get("kind")
            if k == "commitment_open":
                opened += 1
            elif k == "commitment_close":
                closed += 1
            elif k == "reflection_action":
                action_cnt += 1
            elif k == "trait_update":
                m = ev.get("meta") or {}
                d = m.get("delta")
                if isinstance(d, dict):
                    for v in d.values():
                        try:
                            trait_abs += abs(float(v))
                        except Exception:
                            continue
                else:
                    try:
                        trait_abs += abs(float(m.get("delta") or 0.0))
                    except Exception:
                        pass
        efficacy = float(min(1.0, max(0.0, (closed / max(1, opened)))))
        mr_id = _io.append_meta_reflection(
            eventlog,
            window=window,
            opened=opened,
            closed=closed,
            actions=action_cnt,
            trait_delta_abs=trait_abs,
            efficacy=efficacy,
        )
        # Deterministic reward shaping: reflect efficacy as a bandit_reward (component=reflection)
        try:
            _io.append_bandit_reward(
                eventlog,
                component="reflection",
                arm="meta_reflection",
                reward=efficacy,
                source="meta_reflection",
                window=window,
                ref=mr_id,
            )
        except Exception:
            pass
        return mr_id
    except Exception:
        return None


def maybe_emit_self_assessment(eventlog: EventLog, *, window: int = 10) -> int | None:
    """Emit a self_assessment every `window` reflections, idempotently.

    Metrics:
    - opened, closed, actions, trait_delta_abs, efficacy (closed/max(1,opened))
    - avg_close_lag: average tick delta between open and close (within-window pairs)
    - hit_rate: closed/max(1,actions)
    - drift_util: trait_delta_abs/max(1,actions)
    """
    try:
        events = eventlog.read_all()
        # Identify reflection windows by id
        reflections = [e for e in events if e.get("kind") == "reflection"]
        refl_ids = [int(e.get("id") or 0) for e in reflections]
        if len(refl_ids) < int(window):
            return None
        # Define the window as the last `window` reflections, and mark the start
        # boundary as the reflection immediately BEFORE the window (or 0 if none).
        end_id = refl_ids[-1]
        window_ids = refl_ids[-int(window) :]
        if len(refl_ids) > int(window):
            start_id = refl_ids[-int(window) - 1]
        else:
            start_id = 0
        inputs_hash = _sha256_json({"refs": window_ids})
        # Strong idempotency: if a self_assessment with the same inputs_hash exists, skip
        for ev in reversed(events):
            if ev.get("kind") != "self_assessment":
                continue
            m = ev.get("meta") or {}
            if str(m.get("inputs_hash") or "") == inputs_hash:
                return None

        opened = 0
        closed = 0
        action_cnt = 0
        trait_abs = 0.0

        # Track tick progression and compute lag between opens and closes
        tick_no = 0
        open_tick_by_cid: dict[str, int] = {}
        lags: list[int] = []

        for ev in events:
            try:
                eid = int(ev.get("id") or 0)
            except Exception:
                continue
            if ev.get("kind") == "autonomy_tick":
                tick_no += 1
            # Only count metrics strictly within the window (>start_id, <=end_id)
            if eid <= start_id or eid > end_id:
                continue
            k = ev.get("kind")
            if k == "commitment_open":
                opened += 1
                cid = str(((ev.get("meta") or {}).get("cid")) or "")
                if cid:
                    open_tick_by_cid[cid] = tick_no
            elif k == "commitment_close":
                closed += 1
                cid = str(((ev.get("meta") or {}).get("cid")) or "")
                if cid and cid in open_tick_by_cid:
                    lag = max(0, tick_no - int(open_tick_by_cid[cid]))
                    lags.append(int(lag))
            # Treat actions deterministically as reflection-sourced commitment openings
            # Prefer meta.reason=="reflection"; also accept meta.source=="reflection" for forward-compat
            meta_ev = ev.get("meta") or {}
            if k == "commitment_open":
                r = str(meta_ev.get("reason") or "").strip().lower()
                s = str(meta_ev.get("source") or "").strip().lower()
                if r == "reflection" or s == "reflection":
                    action_cnt += 1
            elif k == "trait_update":
                m = ev.get("meta") or {}
                d = m.get("delta")
                if isinstance(d, dict):
                    for v in d.values():
                        try:
                            trait_abs += abs(float(v))
                        except Exception:
                            continue
                else:
                    try:
                        trait_abs += abs(float(m.get("delta") or 0.0))
                    except Exception:
                        pass

        efficacy = float(min(1.0, max(0.0, (closed / max(1, opened)))))
        avg_close_lag = float(sum(lags) / len(lags)) if lags else 0.0
        hit_rate = float(min(1.0, max(0.0, (closed / max(1, action_cnt)))))
        drift_util = float(trait_abs / max(1, action_cnt))

        sa_id = _io.append_self_assessment(
            eventlog,
            window=window,
            window_start_id=start_id,
            window_end_id=end_id,
            inputs_hash=inputs_hash,
            opened=opened,
            closed=closed,
            actions=action_cnt,
            trait_delta_abs=trait_abs,
            efficacy=efficacy,
            avg_close_lag=avg_close_lag,
            hit_rate=hit_rate,
            drift_util=drift_util,
            actions_kind="commitment_open:source=reflection",
        )
        return sa_id
    except Exception as e:
        import logging

        logging.getLogger(__name__).debug(
            f"Failed to emit self_assessment: {e}", exc_info=True
        )
        return None


def apply_self_assessment_policies(eventlog: EventLog) -> int | None:
    """Emit policy_update(component="reflection", source="self_assessment")
    based on latest self_assessment metrics. Idempotent per assessment.

    Does NOT set meta.src_id to avoid interfering with bridge-only CU→PU checks.
    Returns new event id or None if not emitted.
    """
    try:
        events = eventlog.read_all()
        last_sa = None
        for ev in reversed(events):
            if ev.get("kind") == "self_assessment":
                last_sa = ev
                break
        if not last_sa:
            return None
        sa_id = int(last_sa.get("id") or 0)
        # Idempotency: ensure we haven't already applied policy for this assessment
        for ev in reversed(events):
            if ev.get("kind") != "policy_update":
                continue
            m = ev.get("meta") or {}
            if str(m.get("source")) != "self_assessment":
                continue
            try:
                if int(m.get("assessment_id") or 0) == sa_id:
                    return None
            except Exception:
                continue

        # Baseline cadence from current resolved policy (or stage fallback)
        from pmm.runtime.loop import _resolve_reflection_cadence

        min_turns, min_time_s = _resolve_reflection_cadence(events)
        # Stage mark for observability
        try:
            stage_str, _ = StageTracker.infer_stage(events)
        except Exception:
            stage_str = None

        meta = last_sa.get("meta") or {}
        efficacy = float(meta.get("efficacy") or 0.0)
        hit_rate = float(meta.get("hit_rate") or 0.0)
        avg_lag = float(meta.get("avg_close_lag") or 0.0)
        closed = int(meta.get("closed") or 0)

        # Deterministic tweaks: conservative deltas bounded to valid ranges
        new_turns = int(min_turns)
        new_time = int(min_time_s)

        if efficacy >= 0.6 and hit_rate >= 0.5:
            # Doing well → reflect slightly more frequently
            new_turns = max(1, new_turns - 1)
            new_time = max(5, int(round(new_time * 0.9)))
        elif efficacy < 0.2 and hit_rate < 0.2:
            # Underperforming → slow down to reduce churn
            new_turns = new_turns + 1
            new_time = int(round(new_time * 1.15))
        # If closes are happening but lag is high, nudge cadence down a touch
        if closed >= 1 and avg_lag >= 7:
            new_turns = max(1, new_turns - 1)

        # Clamp to global bounds and apply deadband (ignore <10% changes)
        def _clamp(v: int, lo: int, hi: int) -> int:
            try:
                return max(lo, min(int(v), hi))
            except Exception:
                return lo

        prev_turns = int(min_turns)
        prev_time = int(min_time_s)
        new_turns = _clamp(new_turns, 1, 6)
        new_time = _clamp(new_time, 10, 300)

        def _pct_delta(a: int, b: int) -> float:
            try:
                return abs(a - b) / max(1.0, float(a))
            except Exception:
                return 0.0

        if (
            _pct_delta(prev_turns, new_turns) < 0.10
            and _pct_delta(prev_time, new_time) < 0.10
        ):
            return None

        return _io.append_policy_update(
            eventlog,
            component="reflection",
            meta={
                "stage": stage_str,
                "params": {"min_turns": int(new_turns), "min_time_s": int(new_time)},
                "source": "self_assessment",
                "assessment_id": sa_id,
                "prev_policy": {
                    "min_turns": int(prev_turns),
                    "min_time_s": int(prev_time),
                },
                "new_policy": {
                    "min_turns": int(new_turns),
                    "min_time_s": int(new_time),
                },
            },
        )
    except Exception:
        return None


def maybe_rotate_assessment_formula(eventlog: EventLog) -> int | None:
    """Emit an assessment_policy_update(source="meta_assessment") in a round-robin
    fashion every 3 self_assessment events. Idempotent by rotation count.
    Returns new event id or None if not emitted.
    """
    try:
        events = eventlog.read_all()
        # Determine last self_assessment and count up to its window_end scope
        last_sa = None
        for ev in reversed(events):
            if ev.get("kind") == "self_assessment":
                last_sa = ev
                break
        if not last_sa:
            return None
        sa_count = 0
        last_sa_id = int(last_sa.get("id") or 0)
        for ev in events:
            if (
                ev.get("kind") == "self_assessment"
                and int(ev.get("id") or 0) <= last_sa_id
            ):
                sa_count += 1
        if sa_count < 3:
            return None
        expected_rotations = sa_count // 3
        actual_rotations = sum(
            1 for e in events if e.get("kind") == "assessment_policy_update"
        )
        if actual_rotations >= expected_rotations:
            return None
        # Determine formula version: v1 at 3, v2 at 6, v3 at 9, then repeat
        r = expected_rotations % 3
        formula = "v1" if r == 1 else ("v2" if r == 2 else "v3")
        return _io.append_assessment_policy_update(
            eventlog,
            meta={
                "source": "meta_assessment",
                "formula": formula,
                "rotation_index": int(r),
                "index": int(expected_rotations),
                "self_assessment_count": int(sa_count),
            },
        )
    except Exception:
        return None


__all__ = [
    "maybe_emit_meta_reflection",
    "maybe_emit_self_assessment",
    "apply_self_assessment_policies",
    "maybe_rotate_assessment_formula",
]
