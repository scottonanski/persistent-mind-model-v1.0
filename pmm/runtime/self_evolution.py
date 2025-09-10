from __future__ import annotations

from typing import Dict, List, Any


class SelfEvolution:
    """Applies intrinsic, append-only self-evolution policies.

    Policies implemented (Stage 1):
    - Adaptive Reflection Cooldown: adjust novelty threshold based on recent skips/success.
    - Personality Drift (Conscientiousness stub): nudge trait based on recent commitment close rate.
    """

    # Defaults (must match runtime when not previously evolved)
    DEFAULT_NOVELTY_THRESHOLD = 0.2
    NOVELTY_MIN = 0.1
    NOVELTY_MAX = 0.9

    DEFAULT_CONSCIENTIOUSNESS = 0.5

    @staticmethod
    def _last_setting_from_evolution(events: List[Dict], key: str, default: Any) -> Any:
        """Scan evolution events to retrieve the last known value for `key`.
        key examples: 'cooldown.novelty_threshold', 'traits.Conscientiousness'
        """
        val = default
        for ev in events:
            if ev.get("kind") != "evolution":
                continue
            changes = (ev.get("meta") or {}).get("changes") or {}
            if key in changes:
                val = changes[key]
        return val

    @staticmethod
    def _consecutive_tail(events: List[Dict], predicate) -> int:
        cnt = 0
        for ev in reversed(events):
            if predicate(ev):
                cnt += 1
            else:
                break
        return cnt

    @classmethod
    def _adaptive_cooldown(cls, events: List[Dict]) -> Dict[str, Any]:
        changes: Dict[str, Any] = {}

        # Recognize reflection skip events for novelty_low
        def is_skip_novelty_low(ev: Dict) -> bool:
            if ev.get("kind") == "reflection_skip":
                # Optional schema
                reason = (ev.get("content") or "").split(":", 1)[-1].strip()
                return reason == "novelty_low"
            if ev.get("kind") == "debug":
                meta = ev.get("meta") or {}
                return meta.get("reflect_skip") == "novelty_low"
            return False

        def is_reflection(ev: Dict) -> bool:
            return ev.get("kind") == "reflection"

        skips = cls._consecutive_tail(events, is_skip_novelty_low)
        succ = cls._consecutive_tail(events, is_reflection)

        current = cls._last_setting_from_evolution(
            events, "cooldown.novelty_threshold", cls.DEFAULT_NOVELTY_THRESHOLD
        )
        new_val = current
        if skips > 3:
            new_val = max(cls.NOVELTY_MIN, float(current) - 0.05)
        elif succ > 3:
            new_val = min(cls.NOVELTY_MAX, float(current) + 0.05)

        if new_val != current:
            changes["cooldown.novelty_threshold"] = new_val
        return changes

    @classmethod
    def _commitment_drift(cls, events: List[Dict]) -> Dict[str, Any]:
        changes: Dict[str, Any] = {}
        # Collect the last 10 commitment_open cids (in order)
        opens: List[str] = []
        for ev in events:
            if ev.get("kind") == "commitment_open":
                cid = (ev.get("meta") or {}).get("cid")
                if cid:
                    opens.append(cid)
        opens = opens[-10:]
        if not opens:
            return changes

        # Count closes for those cids (exclude expirations for completion rate)
        closed = set()
        open_set = set(opens)
        for ev in events:
            if ev.get("kind") == "commitment_close":
                cid = (ev.get("meta") or {}).get("cid")
                if cid in open_set:
                    closed.add(cid)
        rate = len(closed) / float(len(opens))

        current = cls._last_setting_from_evolution(
            events, "traits.Conscientiousness", cls.DEFAULT_CONSCIENTIOUSNESS
        )
        new_val = current
        if rate > 0.8:
            new_val = min(1.0, float(current) + 0.01)
        elif rate < 0.2:
            new_val = max(0.0, float(current) - 0.01)

        if new_val != current:
            changes["traits.Conscientiousness"] = new_val
        return changes

    @classmethod
    def apply_policies(
        cls, events: List[Dict], metrics: Dict[str, float]
    ) -> tuple[Dict[str, Any], str]:
        """Apply self-evolution rules based on recent events and metrics.
        Return (dict of changes applied, details string for telemetry).
        """
        changes: Dict[str, Any] = {}
        details = []
        # Adaptive reflection cooldown
        cooldown_changes = cls._adaptive_cooldown(events)
        if cooldown_changes:
            changes.update(cooldown_changes)
            details.append(f"Cooldown: {cooldown_changes}")
        # Personality drift stub
        drift_changes = cls._commitment_drift(events)
        if drift_changes:
            changes.update(drift_changes)
            details.append(f"Drift: {drift_changes}")
        # Commitment completion rate
        recent_commits = [e for e in events[-20:] if e.get("kind") == "commitment_open"]
        recent_closes = [e for e in events[-20:] if e.get("kind") == "commitment_close"]
        if recent_commits and not recent_closes:
            changes["reflection_cadence"] = "increase"
            details.append(
                "No commitments closed in last 20 events, suggest increasing reflection cadence."
            )
        # Reflection novelty
        recent_reflections = [e for e in events[-20:] if e.get("kind") == "reflection"]
        if recent_reflections:
            novel = any(
                "novelty" in (e.get("meta") or {}) and (e["meta"]["novelty"] > 0.5)
                for e in recent_reflections
            )
            if not novel:
                changes["reflection_prompt"] = "make more novel"
                details.append(
                    "Recent reflections lack novelty, suggest more creative prompt."
                )
        # User feedback
        feedback = [e for e in events[-20:] if e.get("kind") == "user_feedback"]
        if feedback:
            changes["user_feedback"] = feedback[-1].get("content")
            details.append(f"User feedback: {feedback[-1].get('content')}")
        return changes, "; ".join(details)
