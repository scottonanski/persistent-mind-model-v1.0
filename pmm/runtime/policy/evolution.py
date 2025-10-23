from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EvolutionPolicy:
    """Policy configuration for EvolutionKernel thresholds and behaviors."""

    # Commitment closure rate thresholds for trait adjustments
    closure_rate_high: float = 0.8
    closure_rate_low: float = 0.2
    # Trait adjustment deltas based on closure rates
    conscientiousness_delta_high: float = 0.05
    conscientiousness_delta_low: float = -0.05
    # Reflection trigger thresholds
    ias_threshold: float = 0.3
    gas_threshold: float = 0.3
    open_commitments_threshold: int = 5
    # Event window sizes for analysis
    recent_events_window: int = 50

    def update(self, **kwargs):
        """Update policy parameters with new values.

        Args:
            **kwargs: Key-value pairs of policy parameters to update.
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)


# Default policy instance
DEFAULT_POLICY = EvolutionPolicy()
