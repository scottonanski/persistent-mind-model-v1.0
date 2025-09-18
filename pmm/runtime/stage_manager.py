import hashlib
from typing import Optional
from pmm.storage.eventlog import EventLog
from pmm.constants import EventKinds


class StageManager:
    """Deterministic stage progression manager with digest idempotency."""

    STAGE_ORDER = ["S0", "S1", "S2", "S3", "S4"]

    def __init__(self, eventlog: EventLog):
        self.eventlog = eventlog

    def current_stage(self) -> str:
        """Return the most recent stage, defaulting to S0."""
        events = [
            e for e in self.eventlog.read_all() if e["kind"] == EventKinds.STAGE_UPDATE
        ]
        if not events:
            return "S0"
        return events[-1]["meta"]["to"]

    def snapshot_digest(self) -> str:
        """Digest of the latest stage event for replay consistency."""
        stage = self.current_stage()
        return hashlib.sha256(stage.encode("utf-8")).hexdigest()[:12]

    def _stage_index(self, stage: str) -> int:
        return self.STAGE_ORDER.index(stage)

    def _criteria_met(self, stage: str) -> bool:
        """Deterministic thresholds for stage advancement."""
        refs = [
            e for e in self.eventlog.read_all() if e["kind"] == EventKinds.REFLECTION
        ]
        evols = [
            e for e in self.eventlog.read_all() if e["kind"] == EventKinds.EVOLUTION
        ]
        metrics = [
            e
            for e in self.eventlog.read_all()
            if e["kind"] == EventKinds.METRICS_UPDATE
        ]

        if not metrics:
            return False
        last_metrics = metrics[-1]["meta"]
        ias, gas = last_metrics.get("ias", 0), last_metrics.get("gas", 0)

        # Apply hysteresis buffer ±0.03 to prevent thrashing
        hysteresis = 0.03

        if stage == "S0":
            return (
                len(refs) >= 3
                and len(evols) >= 2
                and ias >= (0.60 + hysteresis)
                and gas >= (0.20 + hysteresis)
            )
        if stage == "S1":
            return (
                len(refs) >= 5
                and len(evols) >= 4
                and ias >= (0.70 + hysteresis)
                and gas >= (0.35 + hysteresis)
            )
        if stage == "S2":
            return (
                len(refs) >= 8
                and len(evols) >= 6
                and ias >= (0.80 + hysteresis)
                and gas >= (0.50 + hysteresis)
            )
        if stage == "S3":
            return (
                len(refs) >= 12
                and len(evols) >= 8
                and ias >= (0.85 + hysteresis)
                and gas >= (0.75 + hysteresis)
            )
        return False

    def check_and_advance(self) -> Optional[str]:
        """Advance stage deterministically if criteria met."""
        current = self.current_stage()
        idx = self._stage_index(current)
        if idx + 1 >= len(self.STAGE_ORDER):
            return None

        next_stage = self.STAGE_ORDER[idx + 1]
        if not self._criteria_met(current):
            return None

        digest = hashlib.sha256(f"{current}->{next_stage}".encode("utf-8")).hexdigest()[
            :12
        ]

        # Check for existing stage update with same digest (idempotency)
        existing = [
            e
            for e in self.eventlog.read_all()
            if e["kind"] == EventKinds.STAGE_UPDATE
            and e["meta"].get("digest") == digest
        ]
        if existing:
            return existing[0]["id"]

        # Emit stage update event
        event_id = self.eventlog.append(
            kind=EventKinds.STAGE_UPDATE,
            content="",
            meta={"from": current, "to": next_stage, "digest": digest},
        )

        # Emit identity lock to prevent churn until next stage
        self.eventlog.append(
            kind=EventKinds.IDENTITY_LOCK,
            content="",
            meta={"stage": next_stage, "digest": digest},
        )

        # Emit policy update for reflection cadence liberalization
        cadence_policy = self._get_cadence_policy(next_stage)
        self.eventlog.append(
            kind=EventKinds.POLICY_UPDATE,
            content="",
            meta={
                "stage": next_stage,
                "reflection_cadence": cadence_policy,
                "digest": digest,
            },
        )

        return str(event_id)

    def _get_cadence_policy(self, stage: str) -> str:
        """Get reflection cadence policy for stage."""
        if stage in ["S0", "S1"]:
            return "liberalized"
        elif stage in ["S2", "S3", "S4"]:
            return "standard"
        return "standard"
