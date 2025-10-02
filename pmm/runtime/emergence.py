"""Advanced Emergence System for PMM.

Implements multi-dimensional emergence scoring with deterministic z-scored metrics:
- IAS (Identity Autonomy Score)
- GAS (Goal Achievement Score)
- Commitment fulfillment rate
- Reflection diversity

Emits emergence_report events with full metadata, idempotent by digest.
Weights stage transitions by composite emergence score.
"""

from __future__ import annotations

import hashlib
import json
import math
from textwrap import dedent
from typing import Any

from pmm.config import REFLECTION_FORCED
from pmm.runtime.pmm_prompts import build_system_msg


class EmergenceScorer:
    """Computes multi-dimensional emergence scores from event ledger."""

    def __init__(self, window_size: int = 50):
        self.window_size = window_size

    def compute_emergence_metrics(self, events: list[dict]) -> dict[str, float]:
        """Compute deterministic emergence metrics from event window.

        Returns:
            Dict with keys: ias_score, gas_score, commitment_score,
            reflection_score, composite_score
        """
        # Use sliding window of recent events
        window = (
            events[-self.window_size :] if len(events) > self.window_size else events
        )

        if not window:
            return {
                "ias_score": 0.0,
                "gas_score": 0.0,
                "commitment_score": 0.0,
                "reflection_score": 0.0,
                "composite_score": 0.0,
            }

        # Extract base IAS/GAS from telemetry
        ias_raw, gas_raw = self._extract_ias_gas(window)

        # Compute commitment fulfillment rate
        commitment_score = self._compute_commitment_fulfillment(window)

        # Compute reflection diversity
        reflection_score = self._compute_reflection_diversity(window)

        # Z-score normalization (deterministic)
        ias_score = self._z_score_normalize(ias_raw, 0.5, 0.2)
        gas_score = self._z_score_normalize(gas_raw, 0.3, 0.15)

        # Composite score (weighted average)
        composite_score = (
            0.3 * ias_score
            + 0.3 * gas_score
            + 0.2 * commitment_score
            + 0.2 * reflection_score
        )

        return {
            "ias_score": float(ias_score),
            "gas_score": float(gas_score),
            "commitment_score": float(commitment_score),
            "reflection_score": float(reflection_score),
            "composite_score": float(composite_score),
        }

    def _extract_ias_gas(self, events: list[dict]) -> tuple[float, float]:
        """Extract most recent IAS/GAS from autonomy_tick or reflection events."""
        for event in reversed(events):
            if event.get("kind") in ["autonomy_tick", "reflection"]:
                telemetry = (event.get("meta") or {}).get("telemetry") or {}
                if "IAS" in telemetry and "GAS" in telemetry:
                    return float(telemetry["IAS"]), float(telemetry["GAS"])

        # Fallback defaults
        return 0.28, 0.03

    def _compute_commitment_fulfillment(self, events: list[dict]) -> float:
        """Compute commitment fulfillment rate (closes/opens ratio)."""
        opens = sum(1 for e in events if e.get("kind") == "commitment_open")
        closes = sum(1 for e in events if e.get("kind") == "commitment_close")

        if opens == 0:
            return 0.5  # Neutral score when no commitments

        fulfillment_rate = closes / opens
        # Normalize to [0, 1] range
        return min(1.0, fulfillment_rate)

    def _compute_reflection_diversity(self, events: list[dict]) -> float:
        """Compute reflection content diversity using vocabulary richness."""
        reflection_texts = []
        for event in events:
            if event.get("kind") == "reflection":
                text = event.get("text", "")
                if text:
                    reflection_texts.append(text.lower())

        if not reflection_texts:
            return 0.0

        # Compute vocabulary diversity (unique words / total words)
        all_words = []
        for text in reflection_texts:
            words = text.split()
            all_words.extend(words)

        if not all_words:
            return 0.0

        unique_words = set(all_words)
        diversity = len(unique_words) / len(all_words)

        # Normalize to reasonable range
        return min(1.0, diversity * 2.0)

    def _z_score_normalize(self, value: float, mean: float, std: float) -> float:
        """Deterministic z-score normalization, clamped to [0, 1]."""
        if std == 0:
            return 0.5

        z_score = (value - mean) / std
        # Convert z-score to [0, 1] using sigmoid-like function
        normalized = 1.0 / (1.0 + math.exp(-z_score))
        return max(0.0, min(1.0, normalized))


class EmergenceManager:
    """Manages emergence scoring and stage transition weighting."""

    def __init__(self, eventlog):
        self.eventlog = eventlog
        self.scorer = EmergenceScorer()

    def generate_emergence_report(self, events: list[dict]) -> dict[str, Any]:
        """Generate emergence report with deterministic digest for idempotency."""
        metrics = self.scorer.compute_emergence_metrics(events)

        # Add metadata
        report = {
            "metrics": metrics,
            "window_size": self.scorer.window_size,
            "event_count": len(events),
            "timestamp": events[-1].get("timestamp") if events else None,
        }

        # Compute deterministic digest for idempotency
        report_json = json.dumps(report, sort_keys=True)
        digest = hashlib.sha256(report_json.encode()).hexdigest()[:16]
        report["digest"] = digest

        return report

    def emit_emergence_report(self, events: list[dict]) -> bool:
        """Emit emergence_report event if not already present (idempotent)."""
        # Filter out existing emergence_report events for digest calculation
        filtered_events = [e for e in events if e.get("kind") != "emergence_report"]
        report = self.generate_emergence_report(filtered_events)
        digest = report["digest"]

        # Check if report with same digest already exists
        try:
            recent_events = events[-10:]  # Check last 10 events for duplicates
            for event in recent_events:
                if event.get("kind") == "emergence_report":
                    event_meta = event.get("meta") or {}
                    if event_meta.get("digest") == digest:
                        return False  # Already exists, skip emission
        except Exception:
            pass

        # Emit new report
        try:
            self.eventlog.append("emergence_report", "", report)
            return True
        except Exception:
            return False

    def compute_stage_transition_weight(
        self, current_stage: str, target_stage: str, events: list[dict]
    ) -> float:
        """Compute stage transition weight based on emergence score.

        Higher emergence scores facilitate upward transitions.
        Lower scores may trigger downward transitions.
        """
        metrics = self.scorer.compute_emergence_metrics(events)
        composite_score = metrics["composite_score"]

        # Stage ordering for transition direction
        stage_order = ["S0", "S1", "S2", "S3", "S4"]

        try:
            current_idx = stage_order.index(current_stage)
            target_idx = stage_order.index(target_stage)
        except ValueError:
            return 0.5  # Neutral weight for unknown stages

        if target_idx > current_idx:
            # Upward transition - weight by emergence score
            # Higher emergence scores get higher weights
            return composite_score
        elif target_idx < current_idx:
            # Downward transition - weight by inverse emergence score
            # Lower emergence scores get higher weights for downward moves
            return 1.0 - composite_score
        else:
            # Same stage - neutral weight
            return 0.5

    def should_trigger_stage_evaluation(self, events: list[dict]) -> bool:
        """Determine if emergence metrics warrant stage evaluation."""
        metrics = self.scorer.compute_emergence_metrics(events)
        composite_score = metrics["composite_score"]

        # Trigger evaluation if composite score is significantly high or low
        return composite_score > 0.7 or composite_score < 0.3


# Legacy PMM-native reflection function (preserved for compatibility)
PMM_TERMS = [
    "ledger",
    "traits",
    "commitment",
    "policy",
    "scene",
    "projection",
    "rebind",
]

ASSIST_BLOCK = ["how can i assist", "journal", "learn more"]


def _contains_any(text: str, terms: list[str]) -> bool:
    t = (text or "").lower()
    return any(term in t for term in terms)


def _score_pmm_relevance(text: str) -> float:
    t = (text or "").lower()
    if not t:
        return 0.0
    hits = sum(1 for k in PMM_TERMS if k in t)
    return min(1.0, hits / max(1, len(PMM_TERMS)))


def _last_policy_params(
    events: list[dict], component: str
) -> tuple[str | None, dict | None]:
    for ev in reversed(events):
        if ev.get("kind") != "policy_update":
            continue
        m = ev.get("meta") or {}
        if str(m.get("component")) == component:
            return m.get("stage"), m.get("params")
    return None, None


def pmm_native_reflection(
    *,
    eventlog,
    llm_generate,
    reason: str = "identity_adopt",
) -> str:
    """
    Generate a reflection constrained to PMM's ontology.
    Appends a 'reflection' event (or a deterministic fallback) and returns the text.
    Also appends a 'debug' marker with forced_reflection_reason.
    """
    try:
        # always mark the attempt for traceability
        eventlog.append(REFLECTION_FORCED, "", {"forced_reflection_reason": reason})
    except Exception:
        pass

    # Pull current state from projection
    try:
        from pmm.storage.projection import build_identity, build_self_model
    except Exception:
        build_identity = build_self_model = None  # type: ignore

    events = []
    try:
        events = eventlog.read_all()
    except Exception:
        events = []

    name = "Assistant"
    openness = conscientiousness = extraversion = agreeableness = neuroticism = 0.5
    open_list: list[str] = []

    try:
        if build_identity is not None:
            ident = build_identity(events)
            nm = str((ident or {}).get("name") or "").strip()
            if nm:
                name = nm
            traits = (ident or {}).get("traits") or {}
            openness = float(traits.get("openness", 0.5))
            conscientiousness = float(traits.get("conscientiousness", 0.5))
            extraversion = float(traits.get("extraversion", 0.5))
            agreeableness = float(traits.get("agreeableness", 0.5))
            neuroticism = float(traits.get("neuroticism", 0.5))
        if build_self_model is not None:
            model = build_self_model(events)
            open_map = (model.get("commitments") or {}).get("open", {})
            for _cid, meta in (open_map or {}).items():
                label = str((meta or {}).get("text") or _cid)
                if label:
                    open_list.append(label)
    except Exception:
        pass

    # metrics snapshot via recent autonomy_tick telemetry if present
    IAS = 0.28  # noqa: N806 - IAS is an acronym
    GAS = 0.03  # noqa: N806 - GAS is an acronym
    try:
        for ev in reversed(events):
            if ev.get("kind") == "autonomy_tick":
                tel = (ev.get("meta") or {}).get("telemetry") or {}
                IAS = float(tel.get("IAS", IAS))  # noqa: N806
                GAS = float(tel.get("GAS", GAS))  # noqa: N806
                break
    except Exception:
        pass

    # cadence gates via policy_update component=reflection
    min_turns, min_time_s = 3, 50
    try:
        _stage, params = _last_policy_params(events, component="reflection")
        if isinstance(params, dict):
            min_turns = (
                int(params.get("min_turns"))
                if params.get("min_turns") is not None
                else min_turns
            )
            min_time_s = (
                int(params.get("min_time_s"))
                if params.get("min_time_s") is not None
                else min_time_s
            )
    except Exception:
        pass

    # drift policy snapshot (optional)
    novelty_threshold = 0.55
    drift_mult = {"O": 1, "C": 1, "N": 1}
    try:
        _s2, params2 = _last_policy_params(events, component="drift")
        if isinstance(params2, dict):
            mult = params2.get("mult") or {}
            drift_mult = {
                "O": float(mult.get("openness", 1)),
                "C": float(mult.get("conscientiousness", 1)),
                "N": float(mult.get("neuroticism", 1)),
            }
    except Exception:
        pass

    # prompt template (ontology-locked)
    prompt = dedent(
        f"""
        You are {name}.
        {build_system_msg('reflection')}
        Treat this as an internal system reflection: stay ledger-grounded and speak in your own voice.
        Mention PMM mechanics only when they directly justify the action you propose.
        Current state:
        - Traits: O={openness:.2f}, C={conscientiousness:.2f}, \
E={extraversion:.2f}, A={agreeableness:.2f}, N={neuroticism:.2f}
        - Metrics: IAS={IAS:.2f}, GAS={GAS:.2f}
        - Open Commitments: {', '.join(open_list) if open_list else 'none'}
        - Reflection Gates: minT={min_turns}, minS={min_time_s}
        - Policy: novelty_threshold={novelty_threshold:.2f}, \
drift_mult=O:{drift_mult.get('O',1)},C:{drift_mult.get('C',1)},N:{drift_mult.get('N',1)}

        TASK: Reflect ONLY on this ledger state and propose ONE concrete system action:
        - open/close a commitment (e.g., "Open a commitment to review priority queue X every 3 ticks")
        - adjust a trait (|Δ| ≤ 0.05)
        - compact a scene
        - update policy/curriculum (e.g., lower novelty_threshold)
        - rebind a commitment to a new priority

        MANDATES:
        1) Stay within PMM ontology (ledger, traits, commitments, policy, scenes, projection, rebind).
        2) Provide exactly ONE action and a one-sentence rationale tied to IAS/GAS/traits/gates/policy.
        3) Do NOT output generic human self-help (journaling, "learn more") or assistant filler ("How can I assist?").

        Output exactly two lines:
        Line1: Action: <one sentence that references the relevant ledger structures>.
        Line2: Why-mechanics: <one sentence explaining the ledger-based justification>.
        """
    ).strip()

    # retry up to 3x if the model drifts from ontology
    for _attempt in range(3):
        try:
            text = str(llm_generate(prompt) or "").strip()
        except Exception:
            text = ""
        if not text:
            continue
        score = _score_pmm_relevance(text)
        bad = _contains_any(text, ASSIST_BLOCK)
        if score >= 0.7 and not bad:
            eventlog.append(
                "reflection", text, {"reason": reason, "relevance_score": score}
            )
            return text
        # tighten prompt deterministically
        prompt = (
            prompt
            + "\nPRIORITY: Use PMM terms (ledger/traits/commitment/policy/scene). Avoid assistant phrases."
        )

    # deterministic fallback (ensures a reflection event exists)
    fallback = (
        "Action: Policy — lower novelty_threshold to 0.50 to increase "
        "reflection frequency.\nWhy-mechanics: Ledger shows low GAS and low "
        "novelty; adjusting policy should surface higher-novelty commitment "
        "adjustments."
    )
    try:
        eventlog.append(
            "reflection",
            fallback,
            {
                "reason": reason,
                "fallback": True,
                "relevance_score": _score_pmm_relevance(fallback),
            },
        )
    except Exception:
        pass
    return fallback
