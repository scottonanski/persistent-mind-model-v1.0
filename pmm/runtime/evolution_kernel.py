from __future__ import annotations

import time as _time
from collections.abc import Sequence
from math import isnan
from typing import Any

from pmm.commitments.tracker import CommitmentTracker
from pmm.runtime.cooldown import ReflectionCooldown
from pmm.runtime.eventlog import EventLog
from pmm.runtime.metrics import get_or_compute_ias_gas
from pmm.runtime.policy.evolution import DEFAULT_POLICY, EvolutionPolicy
from pmm.runtime.snapshot import LedgerSnapshot
from pmm.runtime.traits import normalize_key
from pmm.storage.projection import build_identity, build_self_model


def _clamp01(value: float) -> float:
    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    return value


class EvolutionKernel:
    """Coordinate feedback loops between reflections, commitments, and metrics.

    Responsibilities:
    - Advisory Role: Evaluates the current state of identity, commitments, and
      metrics to propose adjustments to traits or identity.
    - Proposal Generation: Produces trait or identity proposals that autonomy
      components can act upon.
    - Reflection Triggering: May request reflections, but only emits its own
      reflection events when explicitly forced.
    - Non-Mutative: Avoids mutating the ledger beyond forced reflections; other
      changes are surfaced as proposals.
    """

    def __init__(
        self,
        eventlog: EventLog,
        tracker: CommitmentTracker,
        cooldown: ReflectionCooldown,
    ) -> None:
        self.eventlog = eventlog
        self.tracker = tracker
        self.cooldown = cooldown
        self.policy: EvolutionPolicy = DEFAULT_POLICY

    def evaluate_identity_evolution(
        self,
        *,
        snapshot: LedgerSnapshot | None = None,
        events: Sequence[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Evaluate current identity state and propose evolution steps based on
        reflections, commitments, and metrics.

        Args:
            snapshot: Optional LedgerSnapshot to use for evaluation.
            events: Optional sequence of events to use for evaluation.

        Returns:
            Dict containing proposed changes or analysis for identity evolution.
        """
        snapshot_events: Sequence[dict[str, Any]] | None = events
        if snapshot_events is None and snapshot is not None:
            snapshot_events = snapshot.events
        if snapshot_events is None:
            snapshot_events = self.eventlog.read_tail(limit=1000)

        events_list = list(snapshot_events)
        identity = build_identity(events_list)
        self_model = build_self_model(events_list, eventlog=self.eventlog)
        ias, gas = get_or_compute_ias_gas(self.eventlog)
        open_map = self.tracker._open_map_all(events_list)
        open_commitments = [
            {"cid": cid, **(meta or {})} for cid, meta in (open_map or {}).items()
        ]
        traits_now = identity.get("traits") or {}
        trait_key = normalize_key("conscientiousness")
        current_trait = 0.5
        for cand in (trait_key, f"traits.{trait_key}"):
            if cand in traits_now:
                try:
                    current_trait = float(traits_now[cand])
                except Exception:
                    current_trait = 0.5
                break

        proposed_changes: dict[str, Any] = {
            "identity": identity,
            "self_model": self_model,
            "ias": ias,
            "gas": gas,
            "open_commitments": open_commitments,
            "trait_adjustments": {},
            "reflection_needed": False,
        }

        # Analyze commitments for trait adjustments
        if open_commitments:
            closure_rate = self._calculate_commitment_closure_rate(events_list)
            delta = None
            if closure_rate > self.policy.closure_rate_high:
                delta = self.policy.conscientiousness_delta_high
            elif closure_rate < self.policy.closure_rate_low:
                delta = self.policy.conscientiousness_delta_low
            if delta:
                target = _clamp01(current_trait + float(delta))
                proposed_changes["trait_adjustments"][trait_key] = {
                    "delta": float(delta),
                    "target": target,
                }

        # Check if reflection is needed based on metrics and commitments
        if (
            ias < self.policy.ias_threshold
            or gas < self.policy.gas_threshold
            or len(open_commitments) > self.policy.open_commitments_threshold
        ):
            proposed_changes["reflection_needed"] = True

        return proposed_changes

    def _calculate_commitment_closure_rate(
        self, events: Sequence[dict[str, Any]]
    ) -> float:
        """Calculate the rate of commitment closure from recent events.

        Args:
            events: Sequence of recent events from the event log.

        Returns:
            float: Rate of commitment closure (closed / total opened).
        """
        recent_tail = list(events)[-self.policy.recent_events_window :]
        recent_opens = [
            e for e in recent_tail if str(e.get("kind")) == "commitment_open"
        ]
        recent_closes = [
            e for e in recent_tail if str(e.get("kind")) == "commitment_close"
        ]
        if not recent_opens:
            return 0.0

        def _cid_from(event: dict[str, Any]) -> str:
            meta = event.get("meta") or {}
            raw = meta.get("cid")
            if not raw:
                raw = meta.get("commitment_id")
            return str(raw or "")

        open_cids = {cid for cid in (_cid_from(e) for e in recent_opens) if cid}
        closed_cids = {cid for cid in (_cid_from(e) for e in recent_closes) if cid}
        closed_count = len(open_cids & closed_cids)
        return closed_count / len(open_cids) if open_cids else 0.0

    def trigger_reflection_if_needed(
        self,
        *,
        snapshot: LedgerSnapshot | None = None,
        events: Sequence[dict[str, Any]] | None = None,
    ) -> int | None:
        """Emit a reflection event if policy thresholds indicate it’s needed.
        Returns the new event id or None if no emission occurred.
        """
        try:
            evald = self.evaluate_identity_evolution(snapshot=snapshot, events=events)
        except Exception:
            return None

        need = bool(evald.get("reflection_needed"))
        if not need:
            return None

        # Cooldown gate
        try:
            now = float(_time.time())
        except Exception:
            now = 0.0
        # novelty is not computed here; pass 0.0 as neutral
        try:
            ok, _ = self.cooldown.should_reflect(now, 0.0)  # type: ignore[arg-type]
        except Exception:
            ok = True
        if not ok:
            return None

        # Build reflection content + meta
        content = self._generate_reflection_content(evald)
        trait_adjustments = evald.get("trait_adjustments") or {}
        try:
            summary = ", ".join(
                f"{k}:{float(v.get('target', 0.0)):.2f}"
                for k, v in sorted(
                    (
                        (str(k), v if isinstance(v, dict) else {"target": v})
                        for k, v in trait_adjustments.items()
                    ),
                    key=lambda kv: kv[0],
                )
                if not isnan(float(v.get("target", 0.0)))
            )
        except Exception:
            summary = ""
        meta = {
            "source": "evolution_kernel",
            "reason": "policy_thresholds",
            "targets_summary": summary,
        }
        try:
            return self.eventlog.append("reflection", content, meta)
        except Exception:
            return None

    def _generate_reflection_content(self, evaluation: dict[str, Any]) -> str:
        """Generate content for a reflection event based on current evaluation.

        Args:
            evaluation: Dictionary containing the current state and proposed changes.

        Returns:
            str: Content string for the reflection event.
        """
        ias, gas = float(evaluation.get("ias", 0.0)), float(evaluation.get("gas", 0.0))
        open_commitments = evaluation.get("open_commitments", [])
        trait_adjustments = evaluation.get("trait_adjustments", {})

        content_lines = [
            f"Reflecting on current state: IAS={ias:.2f}, GAS={gas:.2f}",
            f"Open commitments: {len(open_commitments)}",
        ]

        if trait_adjustments:
            content_lines.append("Proposed trait adjustments:")
            for trait, payload in trait_adjustments.items():
                data = payload if isinstance(payload, dict) else {"delta": payload}
                try:
                    delta_f = float(data.get("delta", 0.0))
                except Exception:
                    delta_f = 0.0
                try:
                    target_f = float(data.get("target", 0.0))
                except Exception:
                    target_f = 0.0
                content_lines.append(
                    f"- {trait}: delta={delta_f:+.2f} → target={target_f:.2f}"
                )
        else:
            content_lines.append("No trait adjustments proposed at this time.")

        if open_commitments:
            content_lines.append("Key commitments under review:")
            for commit in open_commitments[:3]:
                text = str(commit.get("text") or "Untitled commitment")
                content_lines.append(f"- {text[:50]}...")
        else:
            content_lines.append("No open commitments to review.")

        return "\n".join(content_lines)

    def propose_identity_adjustment(
        self,
        *,
        snapshot: LedgerSnapshot | None = None,
        events: Sequence[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Propose adjustments to identity traits or name based on historical data
        and current metrics.

        Returns:
            Optional[Dict]: Proposed identity adjustments if any, None otherwise.
        """
        evaluation = self.evaluate_identity_evolution(snapshot=snapshot, events=events)
        trait_adjustments = evaluation.get("trait_adjustments", {})
        if not trait_adjustments:
            return None

        # Track historical identity changes for narrative coherence
        if events is None and snapshot is not None:
            events = snapshot.events
        events_list = (
            list(events) if events is not None else self.eventlog.read_tail(limit=1000)
        )
        identity_adoptions = [
            e for e in events_list if str(e.get("kind")) == "identity_adopt"
        ]
        last_adoption = identity_adoptions[-1] if identity_adoptions else None
        adoption_count = len(identity_adoptions)

        # Propose adjustments with narrative context
        targets: dict[str, float] = {}
        traits_map = (
            evaluation.get("identity", {}).get("traits", {}) if evaluation else {}
        )
        for trait, payload in trait_adjustments.items():
            key = normalize_key(trait)
            if not key:
                continue
            if isinstance(payload, dict) and "target" in payload:
                try:
                    targets[key] = _clamp01(float(payload.get("target")))
                    continue
                except Exception:
                    continue
            try:
                seed = traits_map.get(key)
                if seed is None:
                    seed = traits_map.get(f"traits.{key}")
                baseline = float(seed if seed is not None else 0.5)
                delta = float(payload)
            except Exception:
                continue
            targets[key] = _clamp01(baseline + delta)

        if not targets:
            return None

        proposal: dict[str, Any] = {
            "traits": targets,
            "context": {
                "adoption_count": adoption_count,
                "last_adoption_name": (
                    (last_adoption.get("meta") or {}).get("name")
                    if last_adoption
                    else None
                ),
                "ias": evaluation.get("ias"),
                "gas": evaluation.get("gas"),
            },
            "reason": "Based on recent commitment outcomes and metrics",
        }
        return proposal
