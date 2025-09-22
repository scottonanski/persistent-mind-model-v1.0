import re
from typing import Dict, Any


def validate_bot_metrics(
    bot_response: str, actual_metrics: Dict[str, Any], tolerance: float = 0.01
) -> bool:
    """Check if bot-reported IAS/GAS match actual computed metrics (within tolerance).

    Returns True if metrics are consistent (within tolerance) or if no metrics are mentioned.
    Returns False if metrics are mentioned but don't match actual values.
    """
    # Look for IAS=X.XXX, GAS=Y.YYY pattern in response
    match = re.search(r"IAS\s*=\s*([0-9.]+).*GAS\s*=\s*([0-9.]+)", bot_response)
    if not match:
        return True  # no metrics mentioned → not a mismatch

    ias_reported, gas_reported = float(match.group(1)), float(match.group(2))

    # Check if reported values are within tolerance of actual values
    return (
        abs(ias_reported - actual_metrics.get("IAS", 0.0)) <= tolerance
        and abs(gas_reported - actual_metrics.get("GAS", 0.0)) <= tolerance
    )
