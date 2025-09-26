# pmm/runtime/stage_manager.py

from __future__ import annotations
from typing import Any, Optional, TYPE_CHECKING
import logging

from pmm.storage.eventlog import EventLog

if TYPE_CHECKING:
    from pmm.runtime.memegraph import MemeGraphProjection

logger = logging.getLogger(__name__)


class StageManager:
    """Manage stage progression based on deterministic thresholds."""

    def __init__(
        self, eventlog: EventLog, memegraph: Optional["MemeGraphProjection"] = None
    ):
        self.eventlog = eventlog
        self._memegraph = memegraph

    def current_stage(self) -> str:
        if self._memegraph is not None:
            stage_graph = self._memegraph.latest_stage()
            if stage_graph is not None:
                if logger.isEnabledFor(logging.DEBUG):
                    legacy_stage = self._current_stage_legacy()
                    if legacy_stage != stage_graph:
                        logger.debug(
                            "memegraph stage mismatch: legacy=%s graph=%s",
                            legacy_stage,
                            stage_graph,
                        )
                return stage_graph
        return self._current_stage_legacy()

    def _current_stage_legacy(self) -> str:
        """Return the latest recorded stage, defaulting to S0 if none."""
        events = [
            e for e in self.eventlog.read_all() if e.get("kind") == "stage_update"
        ]
        if not events:
            return "S0"
        return events[-1]["meta"]["to"]

    def _criteria_met(
        self,
        stage: str,
        refs: list[dict[str, Any]],
        evols: list[dict[str, Any]],
        introspection_queries: list[dict[str, Any]],
        identity_adoptions: list[dict[str, Any]],
        ias: float,
        gas: float,
        hysteresis: float = 0.03,
    ) -> bool:
        # Calculate synergy bonus for coherent IAS/GAS alignment
        synergy_bonus = min(
            0.1, (ias * gas) ** 0.5 * 0.2
        )  # Up to 10% bonus when aligned
        """
        Deterministic thresholds for stage advancement.
        No reflection quality scoring — count-based only.
        """
        if stage == "S0":
            traditional_criteria = (
                len(refs) >= 2
                and len(evols) >= 1
                and ias >= (0.60 + hysteresis - synergy_bonus)
                and gas >= (0.20 + hysteresis - synergy_bonus)
            )
            introspective_emergence = (
                len(refs) >= 2
                and len(introspection_queries) >= 2
                and len(identity_adoptions) >= 2
                and ias
                and gas
            )
            return traditional_criteria or introspective_emergence

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
