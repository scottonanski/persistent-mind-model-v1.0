"""Self-Model Manager for PMM.

Deterministic personality model management that consolidates trait drift
and ensures personality persistence. All state must be reconstructable
from the event log alone.
"""

from __future__ import annotations

import hashlib
from typing import Any


class SelfModelManager:
    """
    Deterministic personality model manager.
    Maintains and consolidates trait drift into a stable self-model.
    All state must be reconstructable from the event log.
    """

    # Big Five personality traits with full names
    TRAIT_KEYS = {
        "O": "openness",
        "C": "conscientiousness",
        "E": "extraversion",
        "A": "agreeableness",
        "N": "neuroticism",
    }

    # Neutral baseline for all traits
    NEUTRAL_BASELINE = 0.5

    def __init__(self):
        """Initialize the self-model manager."""
        pass

    def project_self_model(self, events: list[dict]) -> dict[str, Any]:
        """
        Pure function.
        Project current self-model deterministically from ledger events:
          - Start from neutral baseline (O=0.50,C=0.50,E=0.50,A=0.50,N=0.50)
          - Apply clamped trait deltas from evolution/policy_update/trait_drift events
          - Clamp each trait ∈ [0.0, 1.0]
        Return current self-model dict with traits + metadata.
        """
        # Start with neutral baseline
        traits = {
            "O": self.NEUTRAL_BASELINE,
            "C": self.NEUTRAL_BASELINE,
            "E": self.NEUTRAL_BASELINE,
            "A": self.NEUTRAL_BASELINE,
            "N": self.NEUTRAL_BASELINE,
        }

        # Track metadata for auditability
        applied_events = []
        last_update_id = None

        # Process events in order to apply trait changes
        for event in events:
            event_kind = event.get("kind", "")
            event_id = event.get("id")
            meta = event.get("meta", {})

            # Normalize helper: maps long names and prefixed keys → single letter codes
            def _norm_trait_key(k: str) -> str:
                k = str(k).strip().lower()
                if k.startswith("traits."):
                    k = k.split(".", 1)[1]
                mapping = {
                    "openness": "O",
                    "conscientiousness": "C",
                    "extraversion": "E",
                    "agreeableness": "A",
                    "neuroticism": "N",
                }
                return mapping.get(k, k.upper()[:1])

            # Process trait_update events
            if event_kind == "trait_update":
                # FIX: normalize multiple formats
                if "trait" in meta and "delta" in meta:
                    t = _norm_trait_key(meta["trait"])
                    d = float(meta["delta"])
                    if t in traits:
                        traits[t] = max(0.0, min(1.0, traits[t] + d))
                        applied_events.append(
                            {
                                "event_id": event_id,
                                "trait": t,
                                "delta": d,
                                "source": "trait_update",
                            }
                        )
                        last_update_id = event_id
                elif "delta" in meta and isinstance(meta["delta"], dict):
                    # Handle multi-delta format: {"delta": {"O": 0.1, "C": -0.05, "E": 0.15}}
                    for t, d in meta["delta"].items():
                        t = _norm_trait_key(t)
                        if t in traits:
                            traits[t] = max(0.0, min(1.0, traits[t] + float(d)))
                            applied_events.append(
                                {
                                    "event_id": event_id,
                                    "trait": t,
                                    "delta": float(d),
                                    "source": "trait_update",
                                }
                            )
                            last_update_id = event_id
                elif "changes" in meta:
                    for t, d in meta["changes"].items():
                        t = _norm_trait_key(t)
                        if t in traits:
                            traits[t] = max(0.0, min(1.0, float(d)))
                            applied_events.append(
                                {
                                    "event_id": event_id,
                                    "trait": t,
                                    "delta": float(d),
                                    "source": "trait_update",
                                }
                            )
                            last_update_id = event_id
                else:
                    # Handle nested trait keys like "traits.conscientiousness"
                    for k, v in meta.items():
                        if k.startswith("traits."):
                            t = _norm_trait_key(k)
                            if t in traits:
                                traits[t] = max(0.0, min(1.0, float(v)))
                                applied_events.append(
                                    {
                                        "event_id": event_id,
                                        "trait": t,
                                        "delta": float(v),
                                        "source": "trait_update",
                                    }
                                )
                                last_update_id = event_id

            # Process policy_update events with trait changes
            elif event_kind == "policy_update":
                component = meta.get("component", "")
                changes = meta.get("changes", [])

                if component == "personality" and isinstance(changes, list):
                    for change in changes:
                        if isinstance(change, dict):
                            trait = _norm_trait_key(change.get("trait", ""))
                            if trait in self.TRAIT_KEYS:
                                try:
                                    delta = float(change.get("delta", 0))
                                    # Clamp delta to reasonable bounds
                                    delta = max(-1.0, min(1.0, delta))
                                    # Apply delta and clamp result to [0.0, 1.0]
                                    traits[trait] = max(
                                        0.0, min(1.0, traits[trait] + delta)
                                    )
                                    applied_events.append(
                                        {
                                            "event_id": event_id,
                                            "trait": trait,
                                            "delta": delta,
                                            "source": "policy_update",
                                        }
                                    )
                                    last_update_id = event_id
                                except (ValueError, TypeError):
                                    continue

            # Process evolution events with trait changes
            elif event_kind == "evolution":
                changes = meta.get("changes", {})
                if isinstance(changes, dict):
                    for key, value in changes.items():
                        # Look for trait keys like "traits.o", "traits.c", etc.
                        if key.startswith("traits."):
                            trait = _norm_trait_key(key)
                            if trait in self.TRAIT_KEYS:
                                try:
                                    # Evolution events typically contain absolute values, not deltas
                                    new_value = float(value)
                                    # Clamp to [0.0, 1.0]
                                    new_value = max(0.0, min(1.0, new_value))
                                    delta = new_value - traits[trait]
                                    traits[trait] = new_value
                                    applied_events.append(
                                        {
                                            "event_id": event_id,
                                            "trait": trait,
                                            "delta": delta,
                                            "source": "evolution",
                                        }
                                    )
                                    last_update_id = event_id
                                except (ValueError, TypeError):
                                    continue

        # Generate deterministic digest of current traits
        trait_str = "|".join(
            f"{k}:{traits[k]:.6f}" for k in sorted(self.TRAIT_KEYS.keys())
        )
        digest = hashlib.sha256(trait_str.encode()).hexdigest()

        return {
            "traits": traits,
            "digest": digest,
            "applied_events": applied_events,
            "last_update_id": last_update_id,
            "event_count": len(applied_events),
        }

    def consolidate(
        self, eventlog, src_event_id: str, current_model: dict[str, Any]
    ) -> str | None:
        """
        Emit a self_model_update event with the full current self-model.
        Event shape:
          kind="self_model_update"
          content="projection"
          meta={
            "component": "self_model_manager",
            "traits": {O,C,E,A,N},
            "digest": <SHA256 over traits>,
            "src_event_id": src_event_id,
            "deterministic": True
          }
        Idempotent: if an event with same digest already exists, do not re-emit.
        Returns event id or None if skipped.
        """
        digest = current_model.get("digest")
        if not digest:
            return None

        # Check for existing event with same digest (idempotency)
        all_events = eventlog.read_all()
        for event in all_events[-20:]:  # Check recent events for efficiency
            if (
                event.get("kind") == "self_model_update"
                and event.get("meta", {}).get("digest") == digest
            ):
                return None  # Skip - already exists

        # Prepare event metadata
        meta = {
            "component": "self_model_manager",
            "traits": current_model.get("traits", {}),
            "digest": digest,
            "src_event_id": src_event_id,
            "deterministic": True,
            "applied_events": len(current_model.get("applied_events", [])),
            "last_update_id": current_model.get("last_update_id"),
        }

        # Emit the consolidation event
        event_id = eventlog.append(
            kind="self_model_update", content="projection", meta=meta
        )

        return event_id

    def detect_anomalies(self, history: list[dict[str, Any]]) -> list[str]:
        """
        Pure function.
        Detect anomalous drift patterns:
          - Trait out of [0,1] bounds (should not happen, but guard)
          - Sudden jump >0.2 between consecutive updates
          - Repeated oscillation (flip-flop >3 times in last N updates)
        Return list of anomaly labels (empty if none).
        """
        anomalies = []

        if not history:
            return anomalies

        # Check each model in history
        for i, model in enumerate(history):
            traits = model.get("traits", {})

            # Check trait bounds
            for trait_key, value in traits.items():
                if not isinstance(value, (int, float)):
                    continue
                if value < 0.0 or value > 1.0:
                    anomalies.append(f"trait_out_of_bounds:{trait_key}:{value:.3f}")

            # Check for sudden jumps between consecutive models
            if i > 0:
                prev_traits = history[i - 1].get("traits", {})
                for trait_key in self.TRAIT_KEYS.keys():
                    if trait_key in traits and trait_key in prev_traits:
                        try:
                            current = float(traits[trait_key])
                            previous = float(prev_traits[trait_key])
                            jump = abs(current - previous)
                            if jump > 0.2:
                                anomalies.append(f"sudden_jump:{trait_key}:{jump:.3f}")
                        except (ValueError, TypeError):
                            continue

        # Check for oscillation patterns (flip-flop >3 times)
        if len(history) >= 4:
            for trait_key in self.TRAIT_KEYS.keys():
                # Extract trait values for this trait across history
                trait_values = []
                for model in history[-8:]:  # Look at last 8 updates
                    traits = model.get("traits", {})
                    if trait_key in traits:
                        try:
                            trait_values.append(float(traits[trait_key]))
                        except (ValueError, TypeError):
                            continue

                # Detect flip-flop pattern (direction changes)
                if len(trait_values) >= 4:
                    direction_changes = 0
                    for i in range(1, len(trait_values) - 1):
                        # Check if direction changed from previous to next
                        prev_diff = trait_values[i] - trait_values[i - 1]
                        next_diff = trait_values[i + 1] - trait_values[i]

                        # Significant direction change (opposite signs and meaningful magnitude)
                        if (
                            prev_diff * next_diff < 0
                            and abs(prev_diff) > 0.05
                            and abs(next_diff) > 0.05
                        ):
                            direction_changes += 1

                    if direction_changes > 3:
                        anomalies.append(f"oscillation:{trait_key}:{direction_changes}")

        return anomalies
